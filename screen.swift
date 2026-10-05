import Foundation
import Darwin
import CoreGraphics
import CoreMedia
import CoreVideo
import ScreenCaptureKit
import Vision

enum Config {
    static let fps = 10
    static let captureWidth = 1280
    static let captureHeight = 800
    static let minimumConfidence: Float = 0.16
    static let minimumTextHeight: Float = 0.007
    static let minimumWidth = 0.008
    static let maximumHeight = 0.18
    static let minimumCharacters = 1
    static let rowVerticalTolerance = 0.032
    static let lineJoinHorizontalGap = 0.12
    static let maxSubtitleLines = 3
    static let maxLineGroupHeight = 0.18
    static let maxLineCenterDistance = 0.30
    static let sameTextThreshold = 0.82
    static let sameTextLooseThreshold = 0.68
    static let changeTextThreshold = 0.55
    static let positionContinuityThreshold = 0.36
    static let strongConfidence: Float = 0.55
    static let strongWidth = 0.24
    static let appearanceConfirmations = 2
    static let appearanceWindow = 0.40
    static let changeConfirmations = 2
    static let changeWindow = 0.45
    static let disappearanceGrace = 0.90
    static let accurateRetryInterval = 0.25
    static let idleVerifyAfter = 0.5
    static let accurateConfidence: Float = 0.28
    static let maxFrameAge = 0.60
    static let historySeconds = 180.0
    static let maxHistoryItems = 300
    static let queryLookback = 30.0
    static let queryLookahead = 0.5
    static let debug = ProcessInfo.processInfo.environment["SNAP_SCREEN_DEBUG"] == "1"
    static let debugInterval = 2.0
    // ROI в координатах Vision (начало снизу слева). По умолчанию: нижние 65% экрана.
    static let roiRect: CGRect = {
        if let raw = ProcessInfo.processInfo.environment["SNAP_SCREEN_ROI"] {
            let values = raw.split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
            if values.count == 4 { return CGRect(x: values[0], y: values[1], width: values[2], height: values[3]) }
        }
        return CGRect(x: 0.0, y: 0.0, width: 1.0, height: 0.65)
    }()
    static let preferredCenterY: Double = {
        if let raw = ProcessInfo.processInfo.environment["SNAP_SCREEN_PREFERRED_Y"], let value = Double(raw) { return value }
        return 0.15
    }()
}

struct RuntimeError: Error, LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

func fmt(_ value: Double) -> String { String(format: "%.3f", value) }
func oneLine(_ text: String) -> String { text.replacingOccurrences(of: "\t", with: " ").replacingOccurrences(of: "\r", with: " ").replacingOccurrences(of: "\n", with: " ") }
func errnoDescription() -> String { String(cString: strerror(errno)) }

let outputLock = NSLock()
var ipcServer: UnixSocketServer?

func out(_ line: String) {
    outputLock.lock()
    print(line)
    fflush(stdout)
    outputLock.unlock()
    ipcServer?.sendLine(line)
}

final class UnixSocketServer {
    private let path: String
    private let stateLock = NSLock()
    private let writeLock = NSLock()
    private var serverFD: Int32 = -1
    private var clientFD: Int32 = -1
    private var stopping = false
    var onLine: ((String) -> Void)?
    var onClientConnected: (() -> Void)?
    var onClientDisconnected: (() -> Void)?

    init(path: String) { self.path = path }
    deinit { stop() }

    private func unlinkSocket() { path.withCString { _ = Darwin.unlink($0) } }

    func start() throws {
        stop()
        let parent = URL(fileURLWithPath: path).deletingLastPathComponent().path
        try FileManager.default.createDirectory(atPath: parent, withIntermediateDirectories: true)
        unlinkSocket()

        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw RuntimeError("socket() failed: " + errnoDescription()) }
        serverFD = fd

        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8)
        let maxPathLength = MemoryLayout.size(ofValue: address.sun_path)
        guard bytes.count < maxPathLength else {
            Darwin.close(fd)
            serverFD = -1
            throw RuntimeError("Unix socket path is too long")
        }

        withUnsafeMutableBytes(of: &address.sun_path) { rawBuffer in
            rawBuffer.initializeMemory(as: UInt8.self, repeating: 0)
            for index in 0..<bytes.count { rawBuffer[index] = bytes[index] }
        }

        let bindResult = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                Darwin.bind(fd, socketAddress, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }

        guard bindResult == 0 else {
            let error = errnoDescription()
            Darwin.close(fd)
            serverFD = -1
            unlinkSocket()
            throw RuntimeError("bind() failed: " + error)
        }

        guard listen(fd, 1) == 0 else {
            let error = errnoDescription()
            Darwin.close(fd)
            serverFD = -1
            unlinkSocket()
            throw RuntimeError("listen() failed: " + error)
        }

        stateLock.lock()
        stopping = false
        stateLock.unlock()

        Thread { [weak self] in self?.acceptLoop() }.start()
    }

    func stop() {
        stateLock.lock()
        if stopping { stateLock.unlock(); return }
        stopping = true
        let server = serverFD
        let client = clientFD
        serverFD = -1
        clientFD = -1
        stateLock.unlock()

        if client >= 0 { Darwin.shutdown(client, SHUT_RDWR); Darwin.close(client) }
        if server >= 0 { Darwin.shutdown(server, SHUT_RDWR); Darwin.close(server) }
        unlinkSocket()
    }

    func sendLine(_ line: String) {
        guard let data = (line + "\n").data(using: .utf8) else { return }
        stateLock.lock()
        let fd = clientFD
        let isStopping = stopping
        stateLock.unlock()
        guard fd >= 0, !isStopping else { return }

        writeLock.lock()
        defer { writeLock.unlock() }
        data.withUnsafeBytes { rawBuffer in
            guard let base = rawBuffer.baseAddress else { return }
            var offset = 0
            while offset < data.count {
                let sent = Darwin.send(fd, base.advanced(by: offset), data.count - offset, 0)
                if sent <= 0 { break }
                offset += sent
            }
        }
    }

    private func acceptLoop() {
        while true {
            stateLock.lock()
            let fd = serverFD
            let isStopping = stopping
            stateLock.unlock()
            if isStopping || fd < 0 { return }

            let accepted = Darwin.accept(fd, nil, nil)
            if accepted < 0 {
                if errno == EINTR { continue }
                stateLock.lock()
                let shouldStop = stopping
                stateLock.unlock()
                if shouldStop { return }
                continue
            }

            stateLock.lock()
            if stopping {
                stateLock.unlock()
                Darwin.close(accepted)
                return
            }
            if clientFD >= 0 { Darwin.shutdown(clientFD, SHUT_RDWR); Darwin.close(clientFD) }
            clientFD = accepted
            stateLock.unlock()

            onClientConnected?()
            readLoop(accepted)

            stateLock.lock()
            if clientFD == accepted { clientFD = -1 }
            let shouldStop = stopping
            stateLock.unlock()

            Darwin.shutdown(accepted, SHUT_RDWR)
            Darwin.close(accepted)
            if !shouldStop { onClientDisconnected?() }
            if shouldStop { return }
        }
    }

    private func readLoop(_ fd: Int32) {
        var buffer = [UInt8](repeating: 0, count: 8192)
        let bufferSize = buffer.count
        var pending = Data()

        while true {
            stateLock.lock()
            let shouldStop = stopping
            stateLock.unlock()
            if shouldStop { return }

            let received = buffer.withUnsafeMutableBytes { rawBuffer -> Int in
                guard let base = rawBuffer.baseAddress else { return -1 }
                return Darwin.recv(fd, base, bufferSize, 0)
            }
            if received == 0 { return }
            if received < 0 { if errno == EINTR { continue }; return }

            pending.append(contentsOf: buffer[0..<received])
            while let newline = pending.firstIndex(of: 10) {
                let lineData = pending.subdata(in: 0..<newline)
                pending.removeSubrange(0...newline)
                guard let line = String(data: lineData, encoding: .utf8) else { continue }
                let cleaned = line.trimmingCharacters(in: .newlines)
                if !cleaned.isEmpty { onLine?(cleaned) }
            }
        }
    }
}

func openScreenRecordingSettings() {
    let urlString = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = [urlString]
    do { try process.run() } catch { out("SCREEN_PERMISSION_SETTINGS_ERROR\t" + error.localizedDescription) }
}

// Диалог и Настройки открываются только один раз за жизнь процесса.
var permissionPrompted = false

func checkScreenRecordingPermission() {
    if CGPreflightScreenCaptureAccess() { out("SCREEN_PERMISSION_GRANTED"); return }
    out("SCREEN_PERMISSION_REQUIRED")
    if permissionPrompted { return }
    permissionPrompted = true
    out("SCREEN_PERMISSION_REQUESTING")
    let result = CGRequestScreenCaptureAccess()
    out("SCREEN_PERMISSION_REQUEST_RESULT\t" + (result ? "granted" : "not_granted"))
    let finalGranted = CGPreflightScreenCaptureAccess()
    out("SCREEN_PERMISSION_STATE\t" + (finalGranted ? "granted" : "not_granted"))
    if !finalGranted { out("SCREEN_PERMISSION_OPENING_SETTINGS"); openScreenRecordingSettings() }
}

func requestScreenRecordingPermission() {
    if Thread.isMainThread { checkScreenRecordingPermission() } else { DispatchQueue.main.sync { checkScreenRecordingPermission() } }
}

enum MachClock {
    private static let timebase: mach_timebase_info_data_t = {
        var info = mach_timebase_info_data_t()
        mach_timebase_info(&info)
        return info
    }()
    static func seconds(_ ticks: UInt64) -> Double {
        guard timebase.denom != 0 else { return 0 }
        return (Double(ticks) * Double(timebase.numer) / Double(timebase.denom)) / 1_000_000_000.0
    }
    static func now() -> Double { seconds(mach_absolute_time()) }
}

struct SubtitleCandidate {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let confidence: Float
    let displayTime: Double?
    let pts: Double
    let wallTime: Double
    var centerX: Double { x + width / 2.0 }
    var centerY: Double { y + height / 2.0 }
}

struct SubtitleInterval {
    let id: Int
    let text: String
    let startWallTime: Double
    var endWallTime: Double?
    let startDisplayTime: Double?
    var lastDisplayTime: Double?
    let confidence: Float
    var x: Double
    var y: Double
    var width: Double
    var height: Double
    var isActive: Bool { endWallTime == nil }
}

final class SubtitleDetector: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private let captureQueue = DispatchQueue(label: "snap.subtitle.capture", qos: .userInitiated)
    private let stateQueue = DispatchQueue(label: "snap.subtitle.state", qos: .userInitiated)
    private let frameSignal = DispatchSemaphore(value: 0)
    private let workerExit = DispatchSemaphore(value: 0)
    private let frameLock = NSLock()

    private var workerRunning = false
    private var workerStopping = false
    private var frameSignalPending = false
    private var latestSampleBuffer: CMSampleBuffer?
    private var latestPTS = 0.0
    private var latestDisplayTime: Double?
    private var latestWallTime: Double?
    private var captureActive = false
    private var shuttingDown = false

    private var subtitleActive = false
    private var currentSubtitle: SubtitleCandidate?
    private var pendingSubtitle: SubtitleCandidate?
    private var pendingCount = 0
    private var pendingStartedAt: Double?
    private var pendingStartedWallTime: Double?
    private var noCandidateSince: Double?
    private var lastConfirmedDisplayTime: Double?
    private var lastProcessedDisplayTime: Double?
    private var lastKnownSubtitleWallTime: Double?
    private var history: [SubtitleInterval] = []
    private var nextIntervalID = 1
    private var lastAccurateRetry = 0.0
    private var receivedFrameCount = 0

    private var frameCount = 0
    private var visionCount = 0
    private var totalVisionTime = 0.0
    private var lastDebugTime = CFAbsoluteTimeGetCurrent()
    private var lastCandidate: SubtitleCandidate?
    private var lastFrameAge: Double?
    private var lastFrameProcessedAt = CFAbsoluteTimeGetCurrent()
    private var missBuffer: CVPixelBuffer?
    private var disappearanceTimer: DispatchSourceTimer?

    func handleCommandLine(_ line: String) {
        let parts = line.components(separatedBy: "\t")
        guard let first = parts.first else { return }
        let command = first.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        switch command {
        case "START":
            Task { do { try await startCapture() } catch { out("START_ERROR\t" + error.localizedDescription) } }
        case "STOP":
            Task { do { try await stopCapture() } catch { out("STOP_ERROR\t" + error.localizedDescription) } }
        case "QUERY":
            guard parts.count >= 3, let wall = Double(parts[2].trimmingCharacters(in: .whitespacesAndNewlines)), wall.isFinite else {
                if parts.count >= 2 { out("SUBTITLE_RESULT\t" + parts[1] + "\t0.000\t0.000\t0.000\t") }
                return
            }
            let requestID = parts[1]
            let strict = parts.count >= 4 && parts[3].trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "strict"
            stateQueue.async { self.handleQuery(id: requestID, wall: wall, strict: strict) }
        case "EXIT":
            Task { await shutdownAndExit() }
        default:
            out("SCREEN_UNKNOWN_COMMAND\t" + oneLine(line))
        }
    }

    func startCapture() async throws {
        guard !shuttingDown else { throw RuntimeError("Subtitle watcher is shutting down") }
        if captureActive { out("SCREEN_ALREADY_STARTED"); return }
        requestScreenRecordingPermission()
        guard CGPreflightScreenCaptureAccess() else { throw RuntimeError("Screen Recording permission is not granted") }

        let content: SCShareableContent
        do { content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true) }
        catch { throw RuntimeError("SCShareableContent failed: " + error.localizedDescription) }

        let mainDisplayID = CGMainDisplayID()
        let display: SCDisplay
        if let mainDisplay = content.displays.first(where: { $0.displayID == mainDisplayID }) { display = mainDisplay }
        else if let firstDisplay = content.displays.first { display = firstDisplay }
        else { throw RuntimeError("No display found") }

        out("Snap Subtitle Watch: display \(Int(display.frame.width))x\(Int(display.frame.height)), capture \(Config.captureWidth)x\(Config.captureHeight), fps \(Config.fps)")
        out("ROI (Vision coords, origin bottom-left) = \(Config.roiRect.origin.x),\(Config.roiRect.origin.y) \(Config.roiRect.size.width)x\(Config.roiRect.size.height), preferredCenterY=\(Config.preferredCenterY)")

        stream = nil
        resetCaptureState()

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let configuration = SCStreamConfiguration()
        configuration.width = Config.captureWidth
        configuration.height = Config.captureHeight
        configuration.preservesAspectRatio = true
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(Config.fps))
        configuration.pixelFormat = kCVPixelFormatType_32BGRA
        configuration.queueDepth = 2
        configuration.showsCursor = false
        configuration.capturesAudio = false

        let newStream = SCStream(filter: filter, configuration: configuration, delegate: self)
        try newStream.addStreamOutput(self, type: .screen, sampleHandlerQueue: captureQueue)
        out("SCREEN_STREAM_OUTPUT_ATTACHED")

        stream = newStream
        startWorker()
        startDisappearanceTimer()
        captureActive = true

        do { try await newStream.startCapture() }
        catch {
            captureActive = false
            markStopping()
            frameSignal.signal()
            disappearanceTimer?.cancel()
            disappearanceTimer = nil
            stream = nil
            waitForWorkerToStop()
            throw RuntimeError("SCStream.startCapture failed: " + error.localizedDescription)
        }

        out("SCREEN_CAPTURE_STARTED")
        out("SCREEN_MONITOR_ON")
        out("SCREEN_STREAM_START_RETURNED")
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 2.0) { [weak self] in self?.reportFrameHealth() }
    }

    private func getReceivedFrameCount() -> Int {
        frameLock.lock()
        let count = receivedFrameCount
        frameLock.unlock()
        return count
    }

    private func reportFrameHealth() {
        frameLock.lock()
        let frames = receivedFrameCount
        let active = captureActive
        frameLock.unlock()
        if active {
            if frames == 0 { out("SCREEN_NO_FRAME_AFTER_2S") }
            else { out("SCREEN_FRAME_HEALTH\tframes=\(frames)") }
        }
    }

    private func resetCaptureState() {
        frameLock.lock()
        workerStopping = false
        frameSignalPending = false
        latestSampleBuffer = nil
        latestPTS = 0
        latestDisplayTime = nil
        latestWallTime = nil
        receivedFrameCount = 0
        frameLock.unlock()

        subtitleActive = false
        currentSubtitle = nil
        clearPending()
        noCandidateSince = nil
        lastConfirmedDisplayTime = nil
        lastProcessedDisplayTime = nil
        lastKnownSubtitleWallTime = nil
        lastAccurateRetry = 0
        lastCandidate = nil
        lastFrameAge = nil
        missBuffer = nil
        frameCount = 0
        visionCount = 0
        totalVisionTime = 0
        lastDebugTime = CFAbsoluteTimeGetCurrent()
        history.removeAll(keepingCapacity: true)
        nextIntervalID = 1
    }

    func stopCapture() async throws {
        guard captureActive else {
            markStopping()
            frameSignal.signal()
            disappearanceTimer?.cancel()
            disappearanceTimer = nil
            stream = nil
            waitForWorkerToStop()
            out("SCREEN_ALREADY_STOPPED")
            return
        }

        captureActive = false
        markStopping()
        frameSignal.signal()

        stateQueue.sync {
            if self.subtitleActive {
                let now = Date().timeIntervalSince1970
                let frameDuration = 1.0 / Double(Config.fps)
                let estimatedEnd = min(now, (self.lastKnownSubtitleWallTime ?? now) + frameDuration)
                self.closeCurrentInterval(atWallTime: estimatedEnd)
            }
            self.subtitleActive = false
            self.currentSubtitle = nil
            self.noCandidateSince = nil
            self.lastKnownSubtitleWallTime = nil
            self.lastConfirmedDisplayTime = nil
            self.clearPending()
        }

        disappearanceTimer?.cancel()
        disappearanceTimer = nil

        if let currentStream = stream {
            do { try await currentStream.stopCapture() }
            catch { out("Stream stop error: " + error.localizedDescription) }
        }

        stream = nil
        waitForWorkerToStop()
        out("SCREEN_CAPTURE_FRAME_COUNT\t\(getReceivedFrameCount())")
        out("SCREEN_MONITOR_OFF")
        out("SCREEN_CAPTURE_STOPPED")
    }

    func shutdownAndExit() async {
        guard !shuttingDown else { exit(0) }
        shuttingDown = true
        if captureActive {
            do { try await stopCapture() }
            catch { out("STOP_ERROR\t" + error.localizedDescription) }
        } else {
            markStopping()
            frameSignal.signal()
            disappearanceTimer?.cancel()
            disappearanceTimer = nil
            stream = nil
            waitForWorkerToStop()
        }
        ipcServer?.stop()
        exit(0)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard captureActive, type == .screen, sampleBuffer.isValid, let status = frameStatus(sampleBuffer) else { return }
        switch status { case .complete, .started, .blank: break; case .idle, .suspended, .stopped: return; default: return }

        frameLock.lock()
        receivedFrameCount += 1
        let currentFrameNumber = receivedFrameCount
        frameLock.unlock()

        if currentFrameNumber == 1 { out("SCREEN_FIRST_FRAME_RECEIVED\tvalid=\(sampleBuffer.isValid)\tstatus=\(status)") }
        if Config.debug && (currentFrameNumber == 10 || currentFrameNumber == 50 || currentFrameNumber % 100 == 0) { out("SCREEN_FRAMES_RECEIVED\t\(currentFrameNumber)") }

        let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
        let displayTime = getDisplayTime(sampleBuffer)
        let machNow = MachClock.now()
        let wallNow = Date().timeIntervalSince1970
        let wallTime = displayTime.map { wallNow - (machNow - $0) } ?? wallNow

        if let displayTime {
            let age = machNow - displayTime
            if age > Config.maxFrameAge {
                if Config.debug { out("Dropped stale frame: age=\(fmt(age * 1000.0))ms") }
                return
            }
        }

        frameLock.lock()
        if workerStopping || !captureActive { frameLock.unlock(); return }
        latestSampleBuffer = sampleBuffer
        latestPTS = pts
        latestDisplayTime = displayTime
        latestWallTime = wallTime
        var shouldSignal = false
        if !frameSignalPending { frameSignalPending = true; shouldSignal = true }
        frameLock.unlock()
        if shouldSignal { frameSignal.signal() }
    }

    private func startWorker() {
        frameLock.lock()
        let oldRunning = workerRunning
        frameLock.unlock()
        if oldRunning { _ = workerExit.wait(timeout: .now() + .milliseconds(1000)) }

        frameLock.lock()
        workerRunning = true
        workerStopping = false
        frameSignalPending = false
        latestSampleBuffer = nil
        latestDisplayTime = nil
        latestWallTime = nil
        frameLock.unlock()

        let thread = Thread { [weak self] in self?.processLatestFrames() }
        thread.name = "snap.subtitle.worker"
        thread.qualityOfService = .userInitiated
        thread.start()
    }

    private func waitForWorkerToStop() {
        frameLock.lock()
        let running = workerRunning
        frameLock.unlock()
        guard running else { return }
        _ = workerExit.wait(timeout: .now() + .milliseconds(1000))
    }

    private func processLatestFrames() {
        defer {
            frameLock.lock()
            workerRunning = false
            workerStopping = false
            frameSignalPending = false
            latestSampleBuffer = nil
            latestDisplayTime = nil
            latestWallTime = nil
            frameLock.unlock()
            workerExit.signal()
        }

        while true {
            frameSignal.wait()
            while true {
                frameLock.lock()
                if workerStopping {
                    frameSignalPending = false
                    latestSampleBuffer = nil
                    latestDisplayTime = nil
                    latestWallTime = nil
                    frameLock.unlock()
                    return
                }

                guard let buffer = latestSampleBuffer else {
                    frameSignalPending = false
                    frameLock.unlock()
                    break
                }

                let pts = latestPTS
                let displayTime = latestDisplayTime
                let wallTime = latestWallTime
                latestSampleBuffer = nil
                latestDisplayTime = nil
                latestWallTime = nil
                frameLock.unlock()

                stateQueue.sync { autoreleasepool { processSampleBuffer(buffer, pts: pts, displayTime: displayTime, wallTime: wallTime) } }

                frameLock.lock()
                if workerStopping {
                    frameSignalPending = false
                    latestSampleBuffer = nil
                    latestDisplayTime = nil
                    latestWallTime = nil
                    frameLock.unlock()
                    return
                }
                if latestSampleBuffer != nil { frameLock.unlock(); continue }
                frameSignalPending = false
                frameLock.unlock()
                break
            }
        }
    }

    private func frameStatus(_ sampleBuffer: CMSampleBuffer) -> SCFrameStatus? {
        guard let array = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]], let attachments = array.first, let rawValue = attachments[.status] as? Int else { return nil }
        return SCFrameStatus(rawValue: rawValue)
    }

    private func getDisplayTime(_ sampleBuffer: CMSampleBuffer) -> Double? {
        guard let array = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]], let attachments = array.first, let ticks = attachments[.displayTime] as? UInt64 else { return nil }
        return MachClock.seconds(ticks)
    }

    private func copyPixelBuffer(_ src: CVPixelBuffer) -> CVPixelBuffer? {
        var dst: CVPixelBuffer?
        let w = CVPixelBufferGetWidth(src), h = CVPixelBufferGetHeight(src)
        guard CVPixelBufferCreate(kCFAllocatorDefault, w, h, CVPixelBufferGetPixelFormatType(src), nil, &dst) == kCVReturnSuccess, let dst else { return nil }
        CVPixelBufferLockBaseAddress(src, .readOnly)
        CVPixelBufferLockBaseAddress(dst, [])
        defer { CVPixelBufferUnlockBaseAddress(src, .readOnly); CVPixelBufferUnlockBaseAddress(dst, []) }
        guard let s = CVPixelBufferGetBaseAddress(src), let d = CVPixelBufferGetBaseAddress(dst) else { return nil }
        let sb = CVPixelBufferGetBytesPerRow(src), db = CVPixelBufferGetBytesPerRow(dst)
        for row in 0..<h { memcpy(d.advanced(by: row * db), s.advanced(by: row * sb), min(sb, db)) }
        return dst
    }

    private func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, pts: Double, displayTime: Double?, wallTime: Double?) {
        let startedAt = CFAbsoluteTimeGetCurrent()
        if let displayTime {
            let age = MachClock.now() - displayTime
            lastFrameAge = age
            if age > Config.maxFrameAge { return }
        } else { lastFrameAge = nil }

        if let displayTime, let lastProcessedDisplayTime, displayTime <= lastProcessedDisplayTime { return }
        if let displayTime { lastProcessedDisplayTime = displayTime }
        lastFrameProcessedAt = startedAt

        if frameStatus(sampleBuffer) == .blank {
            lastCandidate = nil
            registerMissingCandidate(observedAt: startedAt, pixelBuffer: nil)
            frameCount += 1
            printDebugIfNeeded()
            return
        }

        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
            registerMissingCandidate(observedAt: startedAt, pixelBuffer: nil)
            return
        }
        let resolvedWallTime = wallTime ?? Date().timeIntervalSince1970
        let candidate = detectSubtitleWithRecovery(pixelBuffer, pts: pts, displayTime: displayTime, wallTime: resolvedWallTime, now: startedAt)
        lastCandidate = candidate

        if let candidate { noCandidateSince = nil; missBuffer = nil; processCandidate(candidate, observedAt: startedAt) }
        else { registerMissingCandidate(observedAt: startedAt, pixelBuffer: pixelBuffer) }

        totalVisionTime += CFAbsoluteTimeGetCurrent() - startedAt
        visionCount += 1
        frameCount += 1
        printDebugIfNeeded()
    }

    private func registerMissingCandidate(observedAt: Double, pixelBuffer: CVPixelBuffer?) {
        if noCandidateSince == nil { noCandidateSince = observedAt }
        if subtitleActive, let pixelBuffer { missBuffer = copyPixelBuffer(pixelBuffer) }
        clearPending()
    }

    private func detectSubtitleWithRecovery(_ pixelBuffer: CVPixelBuffer, pts: Double, displayTime: Double?, wallTime: Double, now: Double) -> SubtitleCandidate? {
        let fast = detectSubtitle(pixelBuffer, pts: pts, displayTime: displayTime, wallTime: wallTime, recognitionLevel: .fast)
        guard subtitleActive else { return fast }
        guard let fast else {
            guard now - lastAccurateRetry >= Config.accurateRetryInterval else { return nil }
            lastAccurateRetry = now
            return detectSubtitle(pixelBuffer, pts: pts, displayTime: displayTime, wallTime: wallTime, recognitionLevel: .accurate)
        }

        let similarity = currentSubtitle.map { textSimilarity($0.text, fast.text) } ?? 1.0
        let needsRecovery = fast.confidence < Config.accurateConfidence || similarity < Config.sameTextLooseThreshold
        guard needsRecovery, now - lastAccurateRetry >= Config.accurateRetryInterval else { return fast }
        lastAccurateRetry = now
        return detectSubtitle(pixelBuffer, pts: pts, displayTime: displayTime, wallTime: wallTime, recognitionLevel: .accurate) ?? fast
    }

    private func detectSubtitle(_ pixelBuffer: CVPixelBuffer, pts: Double, displayTime: Double?, wallTime: Double, recognitionLevel: VNRequestTextRecognitionLevel) -> SubtitleCandidate? {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = recognitionLevel
        request.usesLanguageCorrection = false
        request.automaticallyDetectsLanguage = true
        request.minimumTextHeight = Config.minimumTextHeight
        // regionOfInterest намеренно НЕ используется: боксы всегда в координатах полного кадра,
        // ROI применяется фильтром ниже.

        let handler = VNImageRequestHandler(cvPixelBuffer: pixelBuffer, orientation: .up, options: [:])
        do { try handler.perform([request]) } catch { return nil }
        guard let observations = request.results, !observations.isEmpty else { return nil }

        let roi = Config.roiRect
        var candidates: [SubtitleCandidate] = []
        for observation in observations {
            guard let topCandidate = observation.topCandidates(1).first else { continue }
            let text = cleanDisplayText(topCandidate.string)
            guard !text.isEmpty, text.count >= Config.minimumCharacters else { continue }
            let confidence = topCandidate.confidence
            guard confidence >= Config.minimumConfidence else { continue }
            let box = observation.boundingBox
            guard box.width >= Config.minimumWidth, box.height <= Config.maximumHeight else { continue }
            guard box.midY >= roi.minY, box.midY <= roi.maxY, box.midX >= roi.minX, box.midX <= roi.maxX else { continue }
            candidates.append(SubtitleCandidate(text: text, x: box.minX, y: box.minY, width: box.width, height: box.height, confidence: confidence, displayTime: displayTime, pts: pts, wallTime: wallTime))
        }
        guard !candidates.isEmpty else { return nil }
        return buildSubtitleCandidate(candidates)
    }

    private func buildSubtitleCandidate(_ observations: [SubtitleCandidate]) -> SubtitleCandidate? {
        let sorted = observations.sorted {
            if abs($0.centerY - $1.centerY) <= Config.rowVerticalTolerance { return $0.x < $1.x }
            return $0.centerY > $1.centerY
        }

        var rows: [[SubtitleCandidate]] = []
        for observation in sorted {
            var attached = false
            for index in rows.indices {
                guard let first = rows[index].first, let last = rows[index].last else { continue }
                let verticalDistance = abs(observation.centerY - first.centerY)
                let tolerance = max(Config.rowVerticalTolerance, max(observation.height, first.height) * 1.35)
                let horizontalGap = observation.x - (last.x + last.width)
                let horizontalOverlap = observation.x <= last.x + last.width
                if verticalDistance <= tolerance && (horizontalOverlap || horizontalGap <= Config.lineJoinHorizontalGap) {
                    rows[index].append(observation)
                    rows[index].sort { $0.x < $1.x }
                    attached = true
                    break
                }
            }
            if !attached { rows.append([observation]) }
        }

        var lineCandidates: [SubtitleCandidate] = []
        for row in rows { if let line = makeCombinedCandidate(row) { lineCandidates.append(line) } }
        guard !lineCandidates.isEmpty else { return nil }

        var blocks: [SubtitleCandidate] = []
        for startIndex in lineCandidates.indices {
            let start = lineCandidates[startIndex]
            var group = [start]
            var previous = start
            let firstNext = startIndex + 1
            if firstNext < lineCandidates.count {
                for nextIndex in firstNext..<lineCandidates.count {
                    let next = lineCandidates[nextIndex]
                    let verticalDistance = abs(previous.centerY - next.centerY)
                    let centerDistance = abs(previous.centerX - next.centerX)
                    if group.count >= Config.maxSubtitleLines || verticalDistance > Config.maxLineGroupHeight || centerDistance > Config.maxLineCenterDistance { break }
                    group.append(next)
                    previous = next
                }
            }
            if group.count == 1 { blocks.append(start) }
            else if let combined = makeCombinedCandidate(group) { blocks.append(combined) }
        }
        guard !blocks.isEmpty else { return nil }
        return chooseSubtitleBlock(blocks)
    }

    private func makeCombinedCandidate(_ items: [SubtitleCandidate]) -> SubtitleCandidate? {
        guard !items.isEmpty else { return nil }
        let ordered = items.sorted {
            if abs($0.centerY - $1.centerY) < Config.rowVerticalTolerance { return $0.x < $1.x }
            return $0.centerY > $1.centerY
        }
        let text = ordered.map { cleanDisplayText($0.text) }.filter { !$0.isEmpty }.joined(separator: " ")
        guard !text.isEmpty else { return nil }
        let minX = ordered.map(\.x).min() ?? 0
        let minY = ordered.map(\.y).min() ?? 0
        let maxX = ordered.map { $0.x + $0.width }.max() ?? 0
        let maxY = ordered.map { $0.y + $0.height }.max() ?? 0
        let confidence = ordered.map { Double($0.confidence) }.reduce(0, +) / Double(ordered.count)
        let displayTime = ordered.compactMap(\.displayTime).max()
        let pts = ordered.map(\.pts).max() ?? 0
        let wallTime = ordered.map(\.wallTime).min() ?? Date().timeIntervalSince1970
        return SubtitleCandidate(text: text, x: minX, y: minY, width: maxX - minX, height: maxY - minY, confidence: Float(confidence), displayTime: displayTime, pts: pts, wallTime: wallTime)
    }

    private func chooseSubtitleBlock(_ candidates: [SubtitleCandidate]) -> SubtitleCandidate? {
        guard !candidates.isEmpty else { return nil }
        var best: SubtitleCandidate?
        var bestScore = -Double.infinity
        for candidate in candidates {
            let confidenceScore = Double(candidate.confidence)
            let widthScore = min(1.0, candidate.width / 0.55)
            let characterScore = min(1.0, Double(candidate.text.count) / 45.0)
            let positionScore = subtitlePositionScore(candidate)
            var score = confidenceScore * 3.0 + widthScore * 2.0 + characterScore * 0.9 + positionScore * 3.0
            if candidate.height <= 0.16 { score += 0.4 }
            if candidate.text.split(separator: " ").count >= 3 { score += 0.6 }
            if let current = currentSubtitle {
                score += textSimilarity(current.text, candidate.text) * 5.0
                score += positionSimilarity(current, candidate) * 2.0
            }
            if let existing = best, textSimilarity(existing.text, candidate.text) >= 0.88 { score += 1.5 }
            if score > bestScore { bestScore = score; best = candidate }
        }
        return best
    }

    private func subtitlePositionScore(_ candidate: SubtitleCandidate) -> Double {
        let yDistance = abs(candidate.centerY - Config.preferredCenterY)
        let yScore = max(0.0, 1.0 - yDistance / 0.38)
        let xDistance = abs(candidate.centerX - 0.5)
        let xScore = max(0.0, 1.0 - xDistance / 0.5)
        return yScore * 0.75 + xScore * 0.25
    }

    private func processCandidate(_ candidate: SubtitleCandidate, observedAt: Double) {
        if let lastConfirmedDisplayTime, let candidateDisplayTime = candidate.displayTime, candidateDisplayTime <= lastConfirmedDisplayTime { return }
        if subtitleActive { processActiveSubtitle(candidate, observedAt: observedAt) }
        else { processAppearance(candidate, observedAt: observedAt) }
    }

    private func processAppearance(_ candidate: SubtitleCandidate, observedAt: Double) {
        if isStrongCandidate(candidate) { activateSubtitle(candidate); return }
        guard let pending = pendingSubtitle else {
            pendingSubtitle = candidate
            pendingCount = 1
            pendingStartedAt = observedAt
            pendingStartedWallTime = candidate.wallTime
            return
        }
        let similarity = textSimilarity(pending.text, candidate.text)
        let position = positionSimilarity(pending, candidate)
        if similarity >= Config.sameTextLooseThreshold && position >= Config.positionContinuityThreshold {
            pendingCount += 1
        } else {
            pendingSubtitle = candidate
            pendingCount = 1
            pendingStartedAt = observedAt
            pendingStartedWallTime = candidate.wallTime
        }
        let age = observedAt - (pendingStartedAt ?? observedAt)
        if pendingCount >= Config.appearanceConfirmations || age >= Config.appearanceWindow {
            activateSubtitle(candidate, startWallTime: pendingStartedWallTime)
        }
    }

    private func activateSubtitle(_ candidate: SubtitleCandidate, startWallTime: Double? = nil) {
        subtitleActive = true
        currentSubtitle = candidate
        lastConfirmedDisplayTime = candidate.displayTime
        noCandidateSince = nil
        clearPending()
        let start = startWallTime ?? candidate.wallTime
        let interval = SubtitleInterval(id: nextIntervalID, text: candidate.text, startWallTime: start, endWallTime: nil, startDisplayTime: candidate.displayTime, lastDisplayTime: candidate.displayTime, confidence: candidate.confidence, x: candidate.x, y: candidate.y, width: candidate.width, height: candidate.height)
        nextIntervalID += 1
        history.append(interval)
        lastKnownSubtitleWallTime = candidate.wallTime
        pruneHistory(referenceWallTime: start)
        out("SUBTITLE_APPEARED\t\(interval.id)\t\(fmt(start))\t\(oneLine(candidate.text))")
    }

    private func processActiveSubtitle(_ candidate: SubtitleCandidate, observedAt: Double) {
        guard let current = currentSubtitle else { activateSubtitle(candidate); return }
        let similarity = textSimilarity(current.text, candidate.text)
        let position = positionSimilarity(current, candidate)
        if similarity >= Config.sameTextThreshold || (similarity >= Config.sameTextLooseThreshold && position >= Config.positionContinuityThreshold) {
            acceptAsCurrent(candidate)
            return
        }
        if isStrongCandidate(candidate) && similarity <= Config.changeTextThreshold {
            commitChange(candidate, previous: current, similarity: similarity)
            return
        }
        guard let pending = pendingSubtitle else {
            pendingSubtitle = candidate
            pendingCount = 1
            pendingStartedAt = observedAt
            pendingStartedWallTime = candidate.wallTime
            return
        }
        let pendingSimilarity = textSimilarity(pending.text, candidate.text)
        let pendingPosition = positionSimilarity(pending, candidate)
        if pendingSimilarity >= Config.sameTextLooseThreshold && pendingPosition >= 0.28 {
            pendingCount += 1
        } else {
            pendingSubtitle = candidate
            pendingCount = 1
            pendingStartedAt = observedAt
            pendingStartedWallTime = candidate.wallTime
            return
        }
        let pendingAge = observedAt - (pendingStartedAt ?? observedAt)
        if pendingCount >= Config.changeConfirmations || pendingAge >= Config.changeWindow { commitChange(candidate, previous: current, similarity: similarity) }
    }

    private func acceptAsCurrent(_ candidate: SubtitleCandidate) {
        currentSubtitle = candidate
        lastConfirmedDisplayTime = candidate.displayTime ?? lastConfirmedDisplayTime
        updateCurrentInterval(with: candidate)
        lastKnownSubtitleWallTime = candidate.wallTime
        clearPending()
    }

    private func commitChange(_ candidate: SubtitleCandidate, previous: SubtitleCandidate, similarity: Double) {
        let changeWallTime = pendingStartedWallTime ?? candidate.wallTime
        closeCurrentInterval(atWallTime: changeWallTime)
        subtitleActive = true
        currentSubtitle = candidate
        lastConfirmedDisplayTime = candidate.displayTime ?? lastConfirmedDisplayTime
        noCandidateSince = nil
        clearPending()
        let interval = SubtitleInterval(id: nextIntervalID, text: candidate.text, startWallTime: changeWallTime, endWallTime: nil, startDisplayTime: candidate.displayTime, lastDisplayTime: candidate.displayTime, confidence: candidate.confidence, x: candidate.x, y: candidate.y, width: candidate.width, height: candidate.height)
        nextIntervalID += 1
        history.append(interval)
        lastKnownSubtitleWallTime = candidate.wallTime
        pruneHistory(referenceWallTime: changeWallTime)
        out("SUBTITLE_CHANGED\t\(interval.id)\t\(fmt(changeWallTime))\t\(oneLine(candidate.text))\tprev=\(oneLine(previous.text))\tsim=\(fmt(similarity))")
    }

    private func updateCurrentInterval(with candidate: SubtitleCandidate) {
        guard let index = history.indices.last, history[index].isActive else { return }
        history[index].lastDisplayTime = candidate.displayTime
        history[index].x = candidate.x
        history[index].y = candidate.y
        history[index].width = max(history[index].width, candidate.width)
        history[index].height = max(history[index].height, candidate.height)
    }

    private func closeCurrentInterval(atWallTime endWallTime: Double) {
        guard let index = history.indices.last, history[index].isActive else { return }
        let start = history[index].startWallTime
        let end = max(start, endWallTime)
        history[index].endWallTime = end
        out("INTERVAL_CLOSED\t\(history[index].id)\t\(fmt(start))\t\(fmt(end))\t\(fmt(end - start))s")
    }

    private func pruneHistory(referenceWallTime: Double) {
        let cutoff = referenceWallTime - Config.historySeconds
        history.removeAll { item in
            guard let end = item.endWallTime else { return false }
            return end < cutoff
        }
        if history.count > Config.maxHistoryItems { history.removeFirst(history.count - Config.maxHistoryItems) }
    }

    private func isStrongCandidate(_ candidate: SubtitleCandidate) -> Bool { candidate.confidence >= Config.strongConfidence || candidate.width >= Config.strongWidth }

    private func clearPending() {
        pendingSubtitle = nil
        pendingCount = 0
        pendingStartedAt = nil
        pendingStartedWallTime = nil
    }

    private func startDisappearanceTimer() {
        disappearanceTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: stateQueue)
        timer.schedule(deadline: .now() + .milliseconds(100), repeating: .milliseconds(100))
        timer.setEventHandler { [weak self] in self?.checkForDisappearance() }
        timer.resume()
        disappearanceTimer = timer
    }

    private func checkForDisappearance() {
        guard captureActive, !workerStopping, subtitleActive, let since = noCandidateSince else { return }
        let now = CFAbsoluteTimeGetCurrent()
        guard now - since >= Config.disappearanceGrace else { return }

        // Кадры идут, и субтитра в них нет: он правда пропал.
        if now - lastFrameProcessedAt < Config.idleVerifyAfter { handleDisappearance(); return }

        // Кадров нет (пауза): тишина в потоке не значит, что субтитр исчез.
        // Проверяем точной OCR на сохранённом кадре. Без кадра ничего не закрываем.
        guard let buffer = missBuffer else { return }
        let wall = Date().timeIntervalSince1970
        if let found = detectSubtitle(buffer, pts: 0, displayTime: nil, wallTime: wall, recognitionLevel: .accurate),
           let current = currentSubtitle,
           textSimilarity(current.text, found.text) >= Config.sameTextLooseThreshold {
            noCandidateSince = nil
            missBuffer = nil
            lastKnownSubtitleWallTime = wall
            out("SUBTITLE_HELD_ON_IDLE\t\(oneLine(found.text))")
            return
        }
        handleDisappearance()
    }

    private func handleDisappearance() {
        guard subtitleActive else { return }
        let now = Date().timeIntervalSince1970
        let frameDuration = 1.0 / Double(Config.fps)
        let end = min(now, (lastKnownSubtitleWallTime ?? now) + frameDuration)
        closeCurrentInterval(atWallTime: end)
        let previous = currentSubtitle
        subtitleActive = false
        currentSubtitle = nil
        noCandidateSince = nil
        lastKnownSubtitleWallTime = nil
        lastConfirmedDisplayTime = nil
        missBuffer = nil
        clearPending()
        out("SUBTITLE_DISAPPEARED\tend=\(fmt(end))\t\(oneLine(previous?.text ?? ""))")
    }

    private func handleQuery(id: String, wall: Double, strict: Bool) {
        guard let interval = findInterval(at: wall, strict: strict) else {
            out("SUBTITLE_RESULT\t\(id)\t0.000\t0.000\t0.000\t")
            return
        }
        let lastSeen = interval.endWallTime ?? lastKnownSubtitleWallTime ?? interval.startWallTime
        let end = interval.endWallTime ?? 0
        out("SUBTITLE_RESULT\t\(id)\t\(fmt(lastSeen))\t\(fmt(interval.startWallTime))\t\(fmt(end))\t\(oneLine(interval.text))")
    }

    private func findInterval(at time: Double, strict: Bool) -> SubtitleInterval? {
        for interval in history.reversed() {
            if time < interval.startWallTime { continue }
            if let end = interval.endWallTime, time > end { continue }
            return interval
        }
        if strict { return nil }
        var best: SubtitleInterval?
        var bestDistance = Double.infinity
        for interval in history {
            let distance: Double
            if time < interval.startWallTime {
                distance = interval.startWallTime - time
                if distance > Config.queryLookahead { continue }
            } else if let end = interval.endWallTime {
                distance = time - end
                if distance > Config.queryLookback { continue }
            } else { continue }
            if distance < bestDistance { bestDistance = distance; best = interval }
        }
        return best
    }

    private func textSimilarity(_ a: String, _ b: String) -> Double {
        let first = comparisonText(a)
        let second = comparisonText(b)
        if first == second { return 1.0 }
        if first.isEmpty || second.isEmpty { return 0.0 }
        let firstChars = Array(first)
        let secondChars = Array(second)
        var previous = Array(0...secondChars.count)
        for i in 1...firstChars.count {
            var current = Array(repeating: 0, count: secondChars.count + 1)
            current[0] = i
            for j in 1...secondChars.count {
                let cost = firstChars[i - 1] == secondChars[j - 1] ? 0 : 1
                current[j] = min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost)
            }
            previous = current
        }
        let distance = previous[secondChars.count]
        let maximumLength = max(firstChars.count, secondChars.count)
        guard maximumLength > 0 else { return 1.0 }
        let editSimilarity = 1.0 - Double(distance) / Double(maximumLength)
        let tokenSimilarity = tokenJaccard(first, second)
        return editSimilarity * 0.78 + tokenSimilarity * 0.22
    }

    private func tokenJaccard(_ a: String, _ b: String) -> Double {
        let first = Set(a.split(separator: " ").map(String.init))
        let second = Set(b.split(separator: " ").map(String.init))
        if first.isEmpty && second.isEmpty { return 1.0 }
        let union = first.union(second).count
        guard union > 0 else { return 1.0 }
        let intersection = first.intersection(second).count
        return Double(intersection) / Double(union)
    }

    private func comparisonText(_ text: String) -> String {
        var output = ""
        for scalar in text.lowercased().unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) { output += String(scalar) } else { output += " " }
        }
        return output.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
    }

    private func cleanDisplayText(_ text: String) -> String {
        text.replacingOccurrences(of: "\n", with: " ").components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func positionSimilarity(_ a: SubtitleCandidate, _ b: SubtitleCandidate) -> Double {
        let xDistance = abs(a.centerX - b.centerX)
        let yDistance = abs(a.centerY - b.centerY)
        let widthDifference = abs(a.width - b.width)
        let heightDifference = abs(a.height - b.height)
        let xScore = max(0.0, 1.0 - xDistance / 0.45)
        let yScore = max(0.0, 1.0 - yDistance / 0.18)
        let widthScore = max(0.0, 1.0 - widthDifference / 0.50)
        let heightScore = max(0.0, 1.0 - heightDifference / 0.16)
        return xScore * 0.25 + yScore * 0.42 + widthScore * 0.23 + heightScore * 0.10
    }

    private func printDebugIfNeeded() {
        guard Config.debug else { return }
        let now = CFAbsoluteTimeGetCurrent()
        guard now - lastDebugTime >= Config.debugInterval else { return }
        let averageMS = visionCount > 0 ? totalVisionTime / Double(visionCount) * 1000.0 : 0.0
        let effectiveFPS = visionCount > 0 ? Double(visionCount) / max(0.001, now - lastDebugTime) : 0.0
        var line = "Stats: frames=\(frameCount) vision=\(visionCount) fps=\(fmt(effectiveFPS)) avg=\(fmt(averageMS))ms active=\(subtitleActive ? "yes" : "no") capture=\(captureActive ? "yes" : "no") received=\(getReceivedFrameCount()) intervals=\(history.count)"
        if let age = lastFrameAge { line += " frame_age=\(fmt(age * 1000))ms" }
        line += lastCandidate.map { " detected=" + oneLine($0.text) } ?? " detected=no"
        out(line)
        frameCount = 0
        visionCount = 0
        totalVisionTime = 0
        lastDebugTime = now
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        captureActive = false
        markStopping()
        frameSignal.signal()
        disappearanceTimer?.cancel()
        disappearanceTimer = nil
        out("SCREEN_STREAM_STOP_ERROR\t" + error.localizedDescription)
        stateQueue.async {
            if self.subtitleActive {
                let now = Date().timeIntervalSince1970
                let duration = 1.0 / Double(Config.fps)
                let end = min(now, (self.lastKnownSubtitleWallTime ?? now) + duration)
                self.closeCurrentInterval(atWallTime: end)
            }
            self.subtitleActive = false
            self.currentSubtitle = nil
            self.noCandidateSince = nil
            self.lastKnownSubtitleWallTime = nil
            self.lastConfirmedDisplayTime = nil
            self.clearPending()
            self.stream = nil
            out("SCREEN_CAPTURE_STOPPED")
        }
    }

    private func markStopping() {
        frameLock.lock()
        workerStopping = true
        latestSampleBuffer = nil
        latestDisplayTime = nil
        latestWallTime = nil
        frameSignalPending = false
        frameLock.unlock()
    }
}

signal(SIGPIPE, SIG_IGN)

func socketPathFromArguments() -> String? {
    let arguments = CommandLine.arguments
    guard let index = arguments.firstIndex(of: "--socket"), index + 1 < arguments.count else { return nil }
    let path = arguments[index + 1].trimmingCharacters(in: .whitespacesAndNewlines)
    return path.isEmpty ? nil : path
}

guard let socketPath = socketPathFromArguments() else {
    fputs("SnapScreen: missing --socket argument\n", stderr)
    exit(1)
}

let server = UnixSocketServer(path: socketPath)
ipcServer = server
let detector = SubtitleDetector()
server.onLine = { [weak detector] line in detector?.handleCommandLine(line) }
server.onClientConnected = {
    out("SCREEN_IPC_CONNECTED")
}
server.onClientDisconnected = { [weak detector] in
    Task { await detector?.shutdownAndExit() }
}

do { try server.start() }
catch {
    fputs("SnapScreen: \(error.localizedDescription)\n", stderr)
    exit(1)
}

out("Snap Subtitle Watch ready.")
out("Socket = " + socketPath)
out("ScreenCaptureKit capture is OFF until START.")

if let i = CommandLine.arguments.firstIndex(of: "--parent-pid"),
   i + 1 < CommandLine.arguments.count,
   let parentPID = Int32(CommandLine.arguments[i + 1]) {
    Thread {
        while true {
            sleep(2)
            if kill(parentPID, 0) != 0 && errno == ESRCH {
                Task { await detector.shutdownAndExit() }
                sleep(5)
                exit(0)
            }
        }
    }.start()
}

DispatchQueue.main.async { requestScreenRecordingPermission() }

RunLoop.main.run()
