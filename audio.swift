import Foundation
import Darwin
import CoreAudio


enum Config {

    static let fallbackSampleRate = 48000.0
    static let channels = 2
    static let bitrate = 160000

    // 180 s * 384 000 B/s ≈ 69 MB.
    static let ringSeconds = 180.0

    // --- Режим "по target" (есть только момент нажатия хоткея) ---
    static let preRoll = 4.5
    // Сколько секунд именно ЗВУКА нужно набрать после target.
    static let postRollActive = 2.5
    // Максимум ждать продолжения речи (реальные секунды).
    static let maxPostWait = 15.0
    // RMS-порог "в чанке есть звук" (~ -48 dBFS).
    static let activeRMS: Float = 0.004
    static let postTailPad = 0.15

    // --- Режим "по интервалу субтитра" (Python шлёт start/end) ---
    static let intervalPadStart = 0.25
    static let intervalPadEnd = 0.35

    // --- Проверка "нулевого" аудио ---
    static let zeroAudioTimeout = 15.0

    // --- Удаление пауз (делается в Swift, до ffmpeg) ---
    //
    // Порог тишины подбирается автоматически по самому клипу:
    //   floor  = 10-й перцентиль уровней окон (фон / тишина)
    //   speech = 90-й перцентиль (речь)
    //   порог  = floor + thresholdRatio * (speech - floor),
    //            зажатый в [thresholdMinDB, thresholdMaxDB]
    // Жёстко задать порог: SNAP_SILENCE_THRESHOLD="-40" (или "-40dB").
    static var silenceThresholdOverrideDB: Double? {
        guard var v = ProcessInfo.processInfo.environment["SNAP_SILENCE_THRESHOLD"],
              !v.isEmpty else {
            return nil
        }

        v = v.lowercased()
            .replacingOccurrences(of: "db", with: "")
            .trimmingCharacters(in: .whitespaces)

        return Double(v)
    }

    static let analysisWindow = 0.02        // окно анализа, сек
    static let minPause = 0.60              // пауза короче — не трогаем
    static let pauseKeepHead = 0.05         // сколько оставить от начала паузы (затухание)
    static let pauseKeepTail = 0.04         // и от конца (чтобы не срезать атаку первого звука)
    static let startKeep = 0.20             // тишина в начале клипа
    static let endKeep = 0.25               // тишина в конце клипа
    static let minIsland = 0.08             // всплеск короче этого между паузами = шум
    static let snapSeconds = 0.004          // швы сдвигаются к ближайшему нулевому пересечению (±4 мс); 0 = выкл
    static let fadeSeconds = 0.0            // фейды на швах; 0 = жёсткий рез без переходов
    static let thresholdRatio = 0.35
    static let thresholdMinDB = -55.0
    static let thresholdMaxDB = -25.0
    static let minDynamicRangeDB: Float = 8.0

    static var isAppMode: Bool {
        CommandLine.arguments.contains("--socket")
    }

    static var socketPath: String {
        if let index = CommandLine.arguments.firstIndex(of: "--socket"),
           index + 1 < CommandLine.arguments.count {
            let value = CommandLine.arguments[index + 1]
            if !value.isEmpty { return value }
        }

        let executable = URL(fileURLWithPath: CommandLine.arguments.first ?? "")
        return executable
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("snap_audio.sock")
            .path
    }

    static var outputDirectory: String {
        if let index = CommandLine.arguments.firstIndex(of: "--audio-dir"),
           index + 1 < CommandLine.arguments.count {
            let value = CommandLine.arguments[index + 1]
            if !value.isEmpty { return value }
        }

        if let value = ProcessInfo.processInfo.environment["SNAP_AUDIO_DIRECTORY"],
           !value.isEmpty {
            return value
        }

        let executable = URL(fileURLWithPath: CommandLine.arguments.first ?? "")
        let addonDirectory = executable
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        return addonDirectory.appendingPathComponent("audio").path
    }

    static var appBundlePath: String {
        let executable = URL(fileURLWithPath: CommandLine.arguments.first ?? "")
        return executable
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path
    }
}


struct SnapError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}


struct AudioChunk {
    let data: Data
    let start: Double        // секунды аудио-таймлайна
    let end: Double
    let startFrame: Int64    // целочисленные кадры — для точной нарезки
    let frames: Int
    let wallStart: Double    // epoch-секунды (из mHostTime + калибровка)
    let wallEnd: Double
    let active: Bool         // есть ли в чанке звук
}


enum WallMapping {
    case ok(Double)
    case tooOld
    case future
}


// MARK: - Time helpers

let machTimebase: mach_timebase_info_data_t = {
    var t = mach_timebase_info_data_t()
    mach_timebase_info(&t)
    return t
}()

func hostSeconds(_ host: UInt64) -> Double {
    Double(host)
        * Double(machTimebase.numer)
        / Double(machTimebase.denom)
        / 1_000_000_000.0
}


// MARK: - Output

func flushStdout() { fflush(stdout) }

func directLog(_ message: String) {
    print("[AUDIO] \(message)")
    flushStdout()
}

func directEmit(_ message: String) {
    print(message)
    flushStdout()
}


// MARK: - Unix socket

func makeSockAddr(_ path: String) -> sockaddr_un? {
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)

    let bytes = Array(path.utf8) + [0]
    let maxLength = MemoryLayout.size(ofValue: address.sun_path)

    guard bytes.count <= maxLength else { return nil }

    withUnsafeMutableBytes(of: &address.sun_path) { buffer in
        buffer.initializeMemory(as: UInt8.self, repeating: 0)
        buffer.copyBytes(from: bytes)
    }

    return address
}

func writeAll(fd: Int32, text: String) {
    guard let data = (text + "\n").data(using: .utf8) else { return }

    data.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { return }
        let bytes = base.assumingMemoryBound(to: UInt8.self)
        var offset = 0

        while offset < data.count {
            let result = write(fd, bytes.advanced(by: offset), data.count - offset)
            if result <= 0 { break }
            offset += result
        }
    }
}


final class UnixSocket {

    let fd: Int32
    private let owns: Bool

    init(fd: Int32, owns: Bool = true) {
        self.fd = fd
        self.owns = owns
    }

    deinit {
        if owns { close(fd) }
    }

    func send(_ text: String) {
        writeAll(fd: fd, text: text)
    }

    func receiveLine() -> String? {
        var result = Data()
        var byte: UInt8 = 0

        while true {
            let count = read(fd, &byte, 1)
            if count <= 0 { return nil }

            if byte == 0x0A {
                return String(data: result, encoding: .utf8)
            }

            result.append(byte)
        }
    }
}


final class UnixSocketServer: @unchecked Sendable {

    let path: String
    private var serverFD: Int32 = -1
    private var clientFD: Int32 = -1
    private let lock = NSLock()

    init(path: String) throws {
        self.path = path
        unlink(path)

        serverFD = socket(AF_UNIX, SOCK_STREAM, 0)

        guard serverFD >= 0 else {
            throw SnapError(message: "Could not create Unix socket")
        }

        guard var address = makeSockAddr(path) else {
            close(serverFD)
            serverFD = -1
            throw SnapError(message: "Unix socket path is too long")
        }

        let bindStatus = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                bind(serverFD, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }

        guard bindStatus == 0 else {
            let errorText = String(cString: strerror(errno))
            close(serverFD)
            serverFD = -1
            unlink(path)
            throw SnapError(message: "Could not bind Unix socket: " + errorText)
        }

        guard listen(serverFD, 1) == 0 else {
            let errorText = String(cString: strerror(errno))
            close(serverFD)
            serverFD = -1
            unlink(path)
            throw SnapError(message: "Could not listen on Unix socket: " + errorText)
        }
    }

    func acceptClient() -> UnixSocket? {
        let fd = accept(serverFD, nil, nil)
        guard fd >= 0 else { return nil }

        lock.lock()
        if clientFD >= 0 { close(clientFD) }
        clientFD = fd
        lock.unlock()

        // Владелец fd — сервер (закрывает в closeAll), а не UnixSocket.
        return UnixSocket(fd: fd, owns: false)
    }

    func send(_ text: String) {
        lock.lock()
        let fd = clientFD

        guard fd >= 0 else {
            lock.unlock()
            return
        }

        writeAll(fd: fd, text: text)
        lock.unlock()
    }

    func closeAll() {
        lock.lock()

        if clientFD >= 0 {
            close(clientFD)
            clientFD = -1
        }

        if serverFD >= 0 {
            close(serverFD)
            serverFD = -1
        }

        lock.unlock()
        unlink(path)
    }

    deinit { closeAll() }
}


var audioIPCServer: UnixSocketServer?


func log(_ message: String) {
    if let server = audioIPCServer {
        server.send("LOG\t[AUDIO] \(message)")
    } else {
        directLog(message)
    }
}

func emit(_ message: String) {
    if let server = audioIPCServer {
        server.send(message)
    } else {
        directEmit(message)
    }
}

func cleanIPCError(_ value: String) -> String {
    value
        .replacingOccurrences(of: "\n", with: " ")
        .replacingOccurrences(of: "\r", with: " ")
        .replacingOccurrences(of: "\t", with: " ")
}

func formatTime(_ value: Double) -> String {
    String(format: "%.3f", value)
}


// MARK: - Core Audio helpers

func propertyAddress(
    _ selector: AudioObjectPropertySelector,
    scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
    element: AudioObjectPropertyElement = kAudioObjectPropertyElementMain
) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: element)
}

func checkStatus(_ status: OSStatus, _ operation: String) throws {
    guard status == noErr else {
        throw SnapError(message: "\(operation) failed: OSStatus=\(status)")
    }
}

func defaultOutputDevice() throws -> AudioDeviceID {
    var deviceID: AudioDeviceID = 0
    var address = propertyAddress(kAudioHardwarePropertyDefaultSystemOutputDevice)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)

    let status = AudioObjectGetPropertyData(
        AudioObjectID(kAudioObjectSystemObject),
        &address, 0, nil, &size, &deviceID
    )

    try checkStatus(status, "Get default output device")

    guard deviceID != kAudioObjectUnknown else {
        throw SnapError(message: "Default output device is unknown")
    }

    return deviceID
}

func deviceUID(_ deviceID: AudioDeviceID) throws -> String {
    var value: Unmanaged<CFString>?
    var address = propertyAddress(kAudioDevicePropertyDeviceUID)
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)

    let status = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &value)
    try checkStatus(status, "Get device UID")

    guard let value else {
        throw SnapError(message: "Device UID is unavailable")
    }

    return value.takeRetainedValue() as String
}

func deviceName(_ deviceID: AudioDeviceID) -> String {
    var value: Unmanaged<CFString>?
    var address = propertyAddress(kAudioObjectPropertyName)
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)

    let status = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &value)

    guard status == noErr, let value else { return "Unknown" }

    return value.takeRetainedValue() as String
}

func outputStreamCount(_ deviceID: AudioDeviceID) -> Int {
    var address = propertyAddress(
        kAudioDevicePropertyStreams,
        scope: kAudioDevicePropertyScopeOutput
    )
    var size: UInt32 = 0

    let status = AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &size)

    guard status == noErr else { return 0 }

    return Int(size / UInt32(MemoryLayout<AudioStreamID>.size))
}

func isDeviceAlive(_ deviceID: AudioDeviceID) -> Bool {
    var alive: UInt32 = 0
    var address = propertyAddress(kAudioDevicePropertyDeviceIsAlive)
    var size = UInt32(MemoryLayout<UInt32>.size)

    let status = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &alive)

    return status == noErr && alive != 0
}

func waitForDeviceAlive(_ deviceID: AudioDeviceID) throws {
    for _ in 0..<50 {
        if isDeviceAlive(deviceID) { return }
        Thread.sleep(forTimeInterval: 0.1)
    }

    throw SnapError(message: "Aggregate device did not become alive")
}

func tapFormat(_ tapID: AudioObjectID) throws -> AudioStreamBasicDescription {
    var format = AudioStreamBasicDescription()
    var address = propertyAddress(kAudioTapPropertyFormat)
    var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)

    let status = AudioObjectGetPropertyData(tapID, &address, 0, nil, &size, &format)
    try checkStatus(status, "Get tap format")

    return format
}


// MARK: - Recorder

final class AudioRecorder: @unchecked Sendable {

    let sampleRate: Double
    let queue: DispatchQueue          // та же очередь, что и у IOProc
    let exportQueue = DispatchQueue(
        label: "snap.audio.export",
        qos: .utility,
        attributes: .concurrent
    )
    let sessionDirectory: URL

    private let bytesPerFrame = MemoryLayout<Float>.size * Config.channels

    // Всё ниже трогается только на `queue`.
    private var ring: [AudioChunk] = []
    private var ringStart = 0
    private var totalFrames: Int64 = 0
    private var callbackCount = 0
    private var finished = false

    // wall = hostSeconds + wallOffset
    private var wallOffset = 0.0
    private var lastCalibHost = 0.0

    // Проверка сигнала.
    private var signalSeen = false
    private var zeroReported = false

    private let clipLock = NSLock()
    private var nextClipID = 1

    init(sampleRate: Double, queue: DispatchQueue) throws {
        self.sampleRate = sampleRate
        self.queue = queue

        let directory = URL(fileURLWithPath: Config.outputDirectory)

        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss-SSS"

        sessionDirectory = directory.appendingPathComponent(
            "session_" + formatter.string(from: Date())
        )

        try FileManager.default.createDirectory(
            at: sessionDirectory,
            withIntermediateDirectories: true
        )

        log("Audio output directory = " + directory.path)
        log("Session directory = " + sessionDirectory.path)
    }

    var callbacks: Int {
        queue.sync { callbackCount }
    }

    func finish() {
        queue.sync { finished = true }
    }

    private var isFinished: Bool {
        queue.sync { finished }
    }

    // MARK: wall-clock -> audio time

    func audioTime(forWall ref: Double, futureTolerance: Double) -> WallMapping {
        queue.sync {
            guard ringStart < ring.count else { return .future }

            let live = ring[ringStart...]

            guard let first = live.first, let last = live.last else {
                return .future
            }

            if ref < first.wallStart - 0.05 { return .tooOld }

            if ref >= last.wallEnd {
                return ref <= last.wallEnd + futureTolerance
                    ? .ok(last.end)
                    : .future
            }

            for c in live where ref < c.wallEnd {
                let offset = min(max(0, ref - c.wallStart), c.end - c.start)
                return .ok(c.start + offset)
            }

            return .ok(last.end)
        }
    }

    private func latestEnd() -> Double? {
        queue.sync { ring.last?.end }
    }

    // MARK: append (вызывается на ioQueue == queue)

    private func analyze(_ data: Data) -> (rms: Float, peak: Float) {
        data.withUnsafeBytes { raw -> (rms: Float, peak: Float) in
            let s = raw.bindMemory(to: Float.self)
            guard s.count > 0 else { return (rms: 0, peak: 0) }

            var sum: Float = 0
            var peak: Float = 0

            for v in s {
                sum += v * v
                let a = abs(v)
                if a > peak { peak = a }
            }

            return (rms: (sum / Float(s.count)).squareRoot(), peak: peak)
        }
    }

    func append(_ data: Data, frames: Int, hostTime: UInt64, hostTimeValid: Bool) {
        guard frames > 0, !data.isEmpty else { return }

        let startFrame = totalFrames
        let start = Double(startFrame) / sampleRate
        let frameDuration = Double(frames) / sampleRate

        // Калибровка wall <-> host раз в 30 с.
        let hostNow = hostSeconds(mach_absolute_time())

        if lastCalibHost == 0 || hostNow - lastCalibHost > 30 {
            wallOffset = Date().timeIntervalSince1970 - hostNow
            lastCalibHost = hostNow
        }

        let hostStart = hostTimeValid
            ? hostSeconds(hostTime)
            : hostNow - frameDuration

        let wallStart = hostStart + wallOffset
        let wallEnd = wallStart + frameDuration

        totalFrames += Int64(frames)
        let end = Double(totalFrames) / sampleRate

        callbackCount += 1

        let level = analyze(data)
        let active = level.rms > Config.activeRMS

        if callbackCount == 1 {
            log("First IO callback received.")
            log("frames=\(frames) bytes=\(data.count)")
            log("time_start=\(formatTime(start)) time_end=\(formatTime(end))")
            log("host_time_valid=\(hostTimeValid)")
            emit("AUDIO_CAPTURE_STARTED")
        }

        checkSignal(peak: level.peak, audioTime: end)

        ring.append(
            AudioChunk(
                data: data,
                start: start,
                end: end,
                startFrame: startFrame,
                frames: frames,
                wallStart: wallStart,
                wallEnd: wallEnd,
                active: active
            )
        )

        let cutoff = end - Config.ringSeconds

        while ringStart < ring.count {
            if ring[ringStart].end >= cutoff { break }
            ringStart += 1
        }

        if ringStart >= 1024 && ringStart * 2 >= ring.count {
            ring.removeFirst(ringStart)
            ringStart = 0
        }

        if callbackCount % 2500 == 0 {
            log(
                "callbacks=\(callbackCount)"
                + " ring_chunks=\(ring.count - ringStart)"
                + " latest_time=\(formatTime(end))"
            )
        }
    }

    // Ждём первый ненулевой сэмпл до zeroAudioTimeout.
    // Ничего не открываем сами — только сообщаем Python.
    private func checkSignal(peak: Float, audioTime: Double) {
        if signalSeen { return }

        if peak > 0.0001 {
            signalSeen = true

            let db = 20.0 * log10(max(Double(peak), 0.0000001))
            log("Signal detected, peak=" + String(format: "%.1f", db) + " dBFS")

            if zeroReported {
                emit("AUDIO_INFO\tsystem\tsignal_detected")
            }

            return
        }

        if audioTime >= Config.zeroAudioTimeout && !zeroReported {
            zeroReported = true

            log(
                "No signal in the first "
                + String(format: "%.0f", Config.zeroAudioTimeout)
                + " s. Either nothing is playing, or "
                + "Screen & System Audio Recording permission is missing."
            )

            emit("AUDIO_ERROR\tsystem\tzero_audio")
        }
    }

    // MARK: select

    // endWall == nil  -> адаптивный post-roll по звуку, окно от target.
    // endWall != nil  -> интервал субтитра: target = начало, endWall = конец.
    func select(requestID: String, word: String, target: Double, endWall: Double?) {

        if let endWall {
            log(
                "Audio selection (interval) start="
                + formatTime(target)
                + " end_wall="
                + String(format: "%.6f", endWall)
            )
        } else {
            log(
                "Audio selection (adaptive) target="
                + formatTime(target)
                + " window_start="
                + formatTime(max(0, target - Config.preRoll))
            )
        }

        exportQueue.async {
            let start: Double
            let end: Double

            if let endWall {
                start = max(0, target - Config.intervalPadStart)
                end = self.waitForWall(endWall + Config.intervalPadEnd)
            } else {
                start = max(0, target - Config.preRoll)
                end = self.waitForActiveSpeech(after: target)
            }

            self.export(requestID: requestID, word: word, start: start, end: end)
        }
    }

    // Ждём, пока аудио-таймлайн дойдёт до указанного wall-времени.
    private func waitForWall(_ wall: Double) -> Double {
        let begin = Date()

        while true {
            switch audioTime(forWall: wall, futureTolerance: 0) {

            case .ok(let t):
                return t

            case .tooOld:
                return latestEnd() ?? 0

            case .future:
                if isFinished
                    || Date().timeIntervalSince(begin) > Config.maxPostWait {

                    log("waitForWall: timeout, using latest audio.")
                    return latestEnd() ?? 0
                }
            }

            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    private func scanActive(after target: Double) -> (hitEnd: Double?, latest: Double) {
        queue.sync {
            let latest = ring.last?.end ?? target
            var acc = 0.0

            if ringStart < ring.count {
                for c in ring[ringStart...] where c.end > target {
                    if c.active { acc += c.end - max(c.start, target) }

                    if acc >= Config.postRollActive {
                        return (hitEnd: c.end, latest: latest)
                    }
                }
            }

            return (hitEnd: nil, latest: latest)
        }
    }

    // Ждём, пока после target наберётся postRollActive секунд звука.
    private func waitForActiveSpeech(after target: Double) -> Double {
        let begin = Date()

        while true {
            let scan = scanActive(after: target)

            if let hit = scan.hitEnd {
                return hit + Config.postTailPad
            }

            if isFinished
                || Date().timeIntervalSince(begin) > Config.maxPostWait {

                log("waitForActiveSpeech: timeout, using latest audio.")
                return scan.latest
            }

            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    // MARK: export

    // Всё считаем в целых кадрах — без дублей и щелчков на стыках.
    private func exactPCMSelection(
        chunks: [AudioChunk],
        start: Double,
        end: Double
    ) throws -> Data {

        let startF = Int64((start * sampleRate).rounded())
        let endF = Int64((end * sampleRate).rounded())

        guard endF > startF else {
            throw SnapError(message: "Invalid audio selection range")
        }

        var raw = Data()
        raw.reserveCapacity(Int(endF - startF) * bytesPerFrame)

        for c in chunks {
            let s = max(startF, c.startFrame)
            let e = min(endF, c.startFrame + Int64(c.frames))

            guard e > s else { continue }

            let b0 = Int(s - c.startFrame) * bytesPerFrame
            let b1 = Int(e - c.startFrame) * bytesPerFrame

            guard b1 <= c.data.count else { continue }

            raw.append(c.data.subdata(in: b0..<b1))
        }

        guard !raw.isEmpty else {
            throw SnapError(message: "No PCM overlapped requested range")
        }

        return raw
    }

    private func export(requestID: String, word: String, start: Double, end: Double) {

        let chunks: [AudioChunk] = queue.sync {
            guard ringStart < ring.count else { return [] }

            return ring[ringStart...].filter { $0.end >= start && $0.start <= end }
        }

        guard !chunks.isEmpty else {
            emit("AUDIO_ERROR\t\(requestID)\tno_audio_overlap")
            return
        }

        clipLock.lock()
        let clipID = nextClipID
        nextClipID += 1
        clipLock.unlock()

        let rawURL = sessionDirectory.appendingPathComponent(
            String(format: "clip_%03d.raw.f32", clipID)
        )

        let finalURL = sessionDirectory.appendingPathComponent(
            String(format: "clip_%03d.m4a", clipID)
        )

        do {
            let raw = try exactPCMSelection(chunks: chunks, start: start, end: end)

            let rawFrames = raw.count / bytesPerFrame
            let rawDuration = Double(rawFrames) / sampleRate

            let trimmed = try removePauses(raw)

            try trimmed.data.write(to: rawURL, options: .atomic)

            log("Raw selection range = \(formatTime(start)) -> \(formatTime(end))")
            log(
                "Selection duration = " + formatTime(rawDuration)
                + " s, after pause removal = "
                + formatTime(rawDuration - trimmed.removed)
                + " s (removed " + formatTime(trimmed.removed)
                + " s, cuts=\(trimmed.cuts))"
            )

            try encode(raw: rawURL, output: finalURL)

            try? FileManager.default.removeItem(at: rawURL)

            guard usable(finalURL) else {
                throw SnapError(message: "Encoded audio file is empty")
            }

            log("Audio clip exported.")
            log("request=" + requestID)
            log("word=" + word)
            log("file=" + finalURL.path)

            emit("AUDIO_CLIP\t" + requestID + "\t" + finalURL.path)

        } catch {
            try? FileManager.default.removeItem(at: rawURL)
            try? FileManager.default.removeItem(at: finalURL)

            emit(
                "AUDIO_ERROR\t"
                + requestID
                + "\t"
                + cleanIPCError(error.localizedDescription)
            )
        }
    }

    // MARK: pause removal

    private struct Run {
        var silent: Bool
        var start: Int   // индекс окна, включительно
        var end: Int     // индекс окна, не включая
    }

    private func buildRuns(_ silent: [Bool]) -> [Run] {
        var runs: [Run] = []
        guard !silent.isEmpty else { return runs }

        var current = Run(silent: silent[0], start: 0, end: 1)

        for i in 1..<silent.count {
            if silent[i] == current.silent {
                current.end = i + 1
            } else {
                runs.append(current)
                current = Run(silent: silent[i], start: i, end: i + 1)
            }
        }

        runs.append(current)
        return runs
    }

    // Уровень каждого окна в dB (по обоим каналам).
    private func windowLevels(_ raw: Data, frames: Int, window: Int) -> [Float] {
        raw.withUnsafeBytes { buf -> [Float] in
            let s = buf.bindMemory(to: Float.self)
            let windowCount = (frames + window - 1) / window
            var levels = [Float](repeating: -120, count: windowCount)

            for w in 0..<windowCount {
                let f0 = w * window
                let f1 = min(frames, f0 + window)

                guard f1 > f0 else { continue }

                var sum: Float = 0

                for i in (f0 * 2)..<(f1 * 2) {
                    sum += s[i] * s[i]
                }

                let meanSquare = sum / Float((f1 - f0) * 2)
                levels[w] = meanSquare > 1e-12 ? 10 * log10(meanSquare) : -120
            }

            return levels
        }
    }

    private func percentile(_ sorted: [Float], _ p: Double) -> Float {
        sorted[Int(Double(sorted.count - 1) * p)]
    }

    // Сдвигает каждый шов к ближайшему нулевому пересечению сигнала
    // (в пределах snapSeconds), чтобы жёсткий рез не давал щелчка.
    private func snapSeams(_ keep: [Range<Int>], raw: Data, frames: Int) -> [Range<Int>] {

        let radius = Int(Config.snapSeconds * sampleRate)

        guard radius > 0, keep.count > 1 else { return keep }

        var result = keep

        raw.withUnsafeBytes { buf in
            let s = buf.bindMemory(to: Float.self)

            func mono(_ i: Int) -> Float {
                (s[i * 2] + s[i * 2 + 1]) * 0.5
            }

            // Граница между кадрами i-1 и i — пересечение нуля?
            func isCrossing(_ i: Int) -> Bool {
                guard i > 0, i < frames else { return false }

                let a = mono(i - 1)
                let b = mono(i)

                return (a <= 0 && b > 0) || (a >= 0 && b < 0)
            }

            func nearest(_ target: Int, lo: Int, hi: Int) -> Int {
                guard hi >= lo else { return target }

                let t = min(max(target, lo), hi)

                if isCrossing(t) { return t }

                for d in 1...radius {
                    let a = t - d
                    let b = t + d

                    if a >= lo && isCrossing(a) { return a }
                    if b <= hi && isCrossing(b) { return b }
                }

                return t
            }

            for k in 0..<(result.count - 1) {
                let left = result[k]
                let right = result[k + 1]

                // Конец левого куска: можно сдвигать внутрь куска
                // или в зазор, но не дальше начала правого.
                let newEnd = nearest(
                    left.upperBound,
                    lo: left.lowerBound + 1,
                    hi: right.lowerBound - 1
                )

                // Начало правого куска: не раньше нового конца левого
                // и не дальше своего конца.
                let newStart = nearest(
                    right.lowerBound,
                    lo: newEnd + 1,
                    hi: right.upperBound - 1
                )

                result[k] = left.lowerBound..<newEnd
                result[k + 1] = newStart..<right.upperBound
            }
        }

        return result
    }

    // Вырезает длинные паузы (сколько бы их ни было), оставляя короткий
    // "хвост" тишины и делая фейды на швах. Короткие естественные паузы
    // (< minPause) не трогаются.
    private func removePauses(_ raw: Data) throws -> (data: Data, removed: Double, cuts: Int) {

        let frames = raw.count / bytesPerFrame
        let window = max(1, Int(sampleRate * Config.analysisWindow))
        let windowSeconds = Double(window) / sampleRate

        let levels = windowLevels(raw, frames: frames, window: window)

        guard levels.count > 2 else { return (raw, 0, 0) }

        let sortedLevels = levels.sorted()
        let floorDB = percentile(sortedLevels, 0.10)
        let speechDB = percentile(sortedLevels, 0.90)

        if speechDB < -70 {
            throw SnapError(message: "Selected audio is silent")
        }

        let threshold: Float

        if let override = Config.silenceThresholdOverrideDB {
            threshold = Float(override)
        } else {
            guard speechDB - floorDB >= Config.minDynamicRangeDB else {
                log(
                    "Pause removal skipped: low dynamic range ("
                    + String(format: "%.1f", speechDB - floorDB) + " dB)."
                )
                return (raw, 0, 0)
            }

            let adaptive = floorDB + (speechDB - floorDB) * Float(Config.thresholdRatio)

            threshold = min(
                max(adaptive, Float(Config.thresholdMinDB)),
                Float(Config.thresholdMaxDB)
            )
        }

        log(
            "Pause removal: floor=" + String(format: "%.1f", floorDB)
            + " dB speech=" + String(format: "%.1f", speechDB)
            + " dB threshold=" + String(format: "%.1f", threshold) + " dB"
        )

        var silent = levels.map { $0 < threshold }

        var runs = buildRuns(silent)

        // Короткий всплеск (щелчок, шум) между двумя длинными паузами —
        // тоже считаем тишиной, иначе он "склеит" паузу.
        let minPauseWindows = Int((Config.minPause / windowSeconds).rounded(.up))
        let minIslandWindows = Int((Config.minIsland / windowSeconds).rounded(.up))

        var changed = false

        if runs.count >= 3 {
            for i in 1..<(runs.count - 1) where !runs[i].silent {
                let length = runs[i].end - runs[i].start
                let before = runs[i - 1].end - runs[i - 1].start
                let after = runs[i + 1].end - runs[i + 1].start

                if length < minIslandWindows
                    && before >= minPauseWindows
                    && after >= minPauseWindows {

                    for w in runs[i].start..<runs[i].end { silent[w] = true }
                    changed = true
                }
            }
        }

        if changed { runs = buildRuns(silent) }

        // Собираем диапазоны кадров, которые остаются.
        let minPauseFrames = Int(Config.minPause * sampleRate)
        let headKeep = Int(Config.pauseKeepHead * sampleRate)
        let tailKeep = Int(Config.pauseKeepTail * sampleRate)
        let startKeep = Int(Config.startKeep * sampleRate)
        let endKeep = Int(Config.endKeep * sampleRate)

        var keep: [Range<Int>] = []

        func add(_ a: Int, _ b: Int) {
            guard b > a else { return }

            if let last = keep.last, last.upperBound == a {
                keep[keep.count - 1] = last.lowerBound..<b
            } else {
                keep.append(a..<b)
            }
        }

        var cuts = 0

        for (i, run) in runs.enumerated() {
            let fs = run.start * window
            let fe = min(run.end * window, frames)
            let length = fe - fs

            if !run.silent {
                add(fs, fe)
                continue
            }

            if runs.count == 1 {
                throw SnapError(message: "Selected audio is silent")
            }

            if i == 0 {
                // Тишина в начале клипа.
                if length > startKeep {
                    add(fe - startKeep, fe)
                    cuts += 1
                } else {
                    add(fs, fe)
                }

            } else if i == runs.count - 1 {
                // Тишина в конце клипа.
                if length > endKeep {
                    add(fs, fs + endKeep)
                    cuts += 1
                } else {
                    add(fs, fe)
                }

            } else if length > minPauseFrames {
                // Длинная пауза внутри: оставляем начало и конец.
                add(fs, fs + headKeep)
                add(fe - tailKeep, fe)
                cuts += 1

            } else {
                // Короткая естественная пауза.
                add(fs, fe)
            }
        }

        keep = snapSeams(keep, raw: raw, frames: frames)

        let keptFrames = keep.reduce(0) { $0 + $1.count }

        guard keptFrames > 0 else {
            throw SnapError(message: "Nothing left after pause removal")
        }

        if keptFrames == frames { return (raw, 0, 0) }

        var out: [Float] = []
        out.reserveCapacity(keptFrames * 2)

        let fade = Int(Config.fadeSeconds * sampleRate)   // 0 -> фейды выключены

        raw.withUnsafeBytes { buf in
            let s = buf.bindMemory(to: Float.self)

            for (k, seg) in keep.enumerated() {
                let outStart = out.count / 2
                let n = seg.count

                out.append(contentsOf: s[(seg.lowerBound * 2)..<(seg.upperBound * 2)])

                let f = min(fade, n / 2)

                if k > 0 {
                    for i in 0..<f {
                        let g = Float(i) / Float(f)
                        out[(outStart + i) * 2] *= g
                        out[(outStart + i) * 2 + 1] *= g
                    }
                }

                if k < keep.count - 1 {
                    for i in 0..<f {
                        let g = Float(i) / Float(f)
                        let index = (outStart + n - 1 - i) * 2
                        out[index] *= g
                        out[index + 1] *= g
                    }
                }
            }
        }

        let data = out.withUnsafeBufferPointer { Data(buffer: $0) }

        return (data, Double(frames - keptFrames) / sampleRate, cuts)
    }

    private func encode(raw: URL, output: URL) throws {

        guard let ffmpeg = findFFmpeg() else {
            throw SnapError(message: "ffmpeg not found")
        }

        try? FileManager.default.removeItem(at: output)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: ffmpeg)

        process.arguments = [
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "f32le",
            "-ar", String(Int(sampleRate)),
            "-ac", String(Config.channels),
            "-i", raw.path,
            "-c:a", "aac",
            "-b:a", String(Config.bitrate),
            output.path
        ]

        let errorPipe = Pipe()
        process.standardError = errorPipe

        try process.run()

        // Читаем stderr ДО waitUntilExit — иначе возможен дедлок на полном пайпе.
        let errorData = errorPipe.fileHandleForReading.readDataToEndOfFile()

        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            let message = String(data: errorData, encoding: .utf8) ?? "ffmpeg failed"
            throw SnapError(message: message)
        }
    }

    private func usable(_ url: URL) -> Bool {
        guard FileManager.default.fileExists(atPath: url.path) else { return false }

        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            let size = (attributes[.size] as? NSNumber)?.int64Value ?? 0
            return size > 1024
        } catch {
            return false
        }
    }

    private func findFFmpeg() -> String? {
        let paths = [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg"
        ]

        for path in paths where FileManager.default.fileExists(atPath: path) {
            return path
        }

        return nil
    }
}


// MARK: - System audio capture

final class SystemAudioCapture: @unchecked Sendable {

    private let ioQueue = DispatchQueue(label: "snap.audio.io", qos: .userInitiated)
    private let commandQueue = DispatchQueue(label: "snap.audio.commands", qos: .userInitiated)

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioDeviceID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var recorder: AudioRecorder?
    private var active = false
    private var sampleRate = Config.fallbackSampleRate

    private var activeDeviceUID: String?
    private var listenerInstalled = false

    func toggle() {
        commandQueue.async {
            if self.active {
                self.stop()
            } else {
                self.startReportingErrors()
            }
        }
    }

    private func startReportingErrors() {
        do {
            try start()
        } catch {
            log("START ERROR: " + error.localizedDescription)
            cleanup()
            active = false
            emit("AUDIO_STATUS\toff")
        }
    }

    // MARK: смена устройства вывода

    private func installDeviceListener() {
        guard !listenerInstalled else { return }
        listenerInstalled = true

        var address = propertyAddress(kAudioHardwarePropertyDefaultSystemOutputDevice)

        let status = AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            commandQueue
        ) { [weak self] _, _ in
            self?.handleOutputChange()
        }

        if status != noErr {
            log("Could not install output-device listener: OSStatus=\(status)")
        }
    }

    private func handleOutputChange() {
        // Листенер уже вызван на commandQueue.
        guard active else { return }

        // Небольшая задержка: macOS часто шлёт несколько событий подряд.
        commandQueue.asyncAfter(deadline: .now() + 0.6) { [weak self] in
            guard let self, self.active else { return }

            guard
                let output = try? defaultOutputDevice(),
                let uid = try? deviceUID(output),
                uid != self.activeDeviceUID
            else {
                return
            }

            log("Default output changed -> restarting tap.")

            self.cleanup()
            self.active = false

            emit("AUDIO_WARNING\tsystem\toutput_changed_ring_reset")

            self.startReportingErrors()
        }
    }

    // MARK: start / stop

    func start() throws {
        guard !active else { return }

        log("Starting Core Audio device-scoped tap.")

        if Bundle.main.object(forInfoDictionaryKey: "NSAudioCaptureUsageDescription") == nil {
            log("WARNING: NSAudioCaptureUsageDescription is missing.")
        } else {
            log("System-audio usage description is present.")
        }

        let output = try defaultOutputDevice()
        let uid = try deviceUID(output)
        let name = deviceName(output)
        let streams = outputStreamCount(output)

        log("Default output device = " + name)
        log("Default output UID = " + uid)
        log("Output stream count = \(streams)")

        guard streams > 0 else {
            throw SnapError(message: "Output device has no output streams")
        }

        let streamIndex: UInt = 0

        let tapDescription = CATapDescription(
            excludingProcesses: [],
            deviceUID: uid,
            stream: streamIndex
        )

        tapDescription.name = "Snap System Audio Tap"
        tapDescription.isPrivate = true
        tapDescription.isExclusive = true
        tapDescription.isMixdown = true
        tapDescription.isMono = false
        tapDescription.muteBehavior = .unmuted

        log("Tap target device = " + uid)

        var newTapID = AudioObjectID(kAudioObjectUnknown)

        try checkStatus(
            AudioHardwareCreateProcessTap(tapDescription, &newTapID),
            "AudioHardwareCreateProcessTap"
        )

        tapID = newTapID

        log("Process tap created. Tap ID = \(tapID)")
        log("Tap UUID = " + tapDescription.uuid.uuidString)

        let format = try tapFormat(tapID)

        sampleRate = format.mSampleRate > 0
            ? format.mSampleRate
            : Config.fallbackSampleRate

        let channels = Int(format.mChannelsPerFrame)
        let bits = Int(format.mBitsPerChannel)
        let floating = (format.mFormatFlags & kAudioFormatFlagIsFloat) != 0
        let nonInterleaved = (format.mFormatFlags & kAudioFormatFlagIsNonInterleaved) != 0

        log(
            "Tap format: rate=\(sampleRate) ch=\(channels) bits=\(bits)"
            + " float=\(floating) non_interleaved=\(nonInterleaved)"
            + " bytes_per_frame=\(format.mBytesPerFrame)"
        )

        guard floating else { throw SnapError(message: "Tap format is not Float32") }
        guard bits == 32 else { throw SnapError(message: "Tap format is not 32-bit") }
        guard !nonInterleaved else { throw SnapError(message: "Tap format is non-interleaved") }
        guard channels == 2 else {
            throw SnapError(message: "Expected stereo tap, got \(channels) channels")
        }

        let aggregateUID = "com.snap.audio.aggregate." + UUID().uuidString

        let aggregateDescription: [String: Any] = [
            kAudioAggregateDeviceNameKey: "Snap Audio Aggregate",
            kAudioAggregateDeviceUIDKey: aggregateUID,
            kAudioAggregateDeviceMainSubDeviceKey: uid,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [
                [kAudioSubDeviceUIDKey: uid]
            ],
            kAudioAggregateDeviceTapListKey: [
                [
                    kAudioSubTapDriftCompensationKey: true,
                    kAudioSubTapUIDKey: tapDescription.uuid.uuidString
                ]
            ]
        ]

        var newAggregateID = AudioDeviceID(kAudioObjectUnknown)

        try checkStatus(
            AudioHardwareCreateAggregateDevice(
                aggregateDescription as CFDictionary,
                &newAggregateID
            ),
            "AudioHardwareCreateAggregateDevice"
        )

        aggregateID = newAggregateID

        log("Aggregate device created. ID = \(aggregateID)")
        log("Aggregate UID = " + aggregateUID)

        try waitForDeviceAlive(aggregateID)

        log("Aggregate device is alive.")

        let newRecorder = try AudioRecorder(sampleRate: sampleRate, queue: ioQueue)
        recorder = newRecorder

        var newIOProcID: AudioDeviceIOProcID?

        let ioStatus = AudioDeviceCreateIOProcIDWithBlock(
            &newIOProcID,
            aggregateID,
            ioQueue
        ) { [weak newRecorder] _, inputData, inputTime, _, _ in

            guard let recorder = newRecorder else { return }

            let buffers = UnsafeMutableAudioBufferListPointer(
                UnsafeMutablePointer(mutating: inputData)
            )

            guard buffers.count == 1 else { return }

            let buffer = buffers[0]

            guard buffer.mNumberChannels == 2, let pointer = buffer.mData else { return }

            let bytes = Int(buffer.mDataByteSize)
            guard bytes > 0 else { return }

            let frameSize = MemoryLayout<Float>.size * 2
            let frames = bytes / frameSize
            guard frames > 0 else { return }

            let data = Data(bytes: pointer, count: frames * frameSize)

            let stamp = inputTime.pointee
            let hostValid = stamp.mFlags.contains(.hostTimeValid)

            recorder.append(
                data,
                frames: frames,
                hostTime: stamp.mHostTime,
                hostTimeValid: hostValid
            )
        }

        try checkStatus(ioStatus, "AudioDeviceCreateIOProcIDWithBlock")

        guard let newIOProcID else {
            throw SnapError(message: "IOProc ID was not created")
        }

        ioProcID = newIOProcID

        log("IOProc created.")

        try checkStatus(
            AudioDeviceStart(aggregateID, newIOProcID),
            "AudioDeviceStart"
        )

        log("AudioDeviceStart succeeded.")

        activeDeviceUID = uid
        active = true

        installDeviceListener()

        emit("AUDIO_STATUS\ton")

        log("Core Audio tap is ON. Sample rate = \(sampleRate)")
        log("ScreenCaptureKit = disabled. No screen capture is running.")

        let healthRecorder = newRecorder

        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 3.0) {
            self.commandQueue.async {
                guard
                    self.active,
                    let current = self.recorder,
                    current === healthRecorder
                else {
                    return
                }

                let count = healthRecorder.callbacks

                if count == 0 {
                    log("ERROR: zero IO callbacks after 3 seconds.")
                    emit("AUDIO_ERROR\tsystem\tno_io_callbacks")
                } else {
                    log("IO callback health check passed. callbacks=\(count)")
                }
            }
        }
    }

    func stop() {
        guard active else {
            cleanup()
            emit("AUDIO_STATUS\toff")
            return
        }

        log("Stopping Core Audio tap...")

        cleanup()
        active = false

        emit("AUDIO_STATUS\toff")

        log("Core Audio tap is OFF.")
    }

    private func cleanup() {
        if let ioProcID, aggregateID != kAudioObjectUnknown {
            log("AudioDeviceStop status=\(AudioDeviceStop(aggregateID, ioProcID))")
            log("AudioDeviceDestroyIOProcID status=\(AudioDeviceDestroyIOProcID(aggregateID, ioProcID))")
        }

        ioProcID = nil

        if aggregateID != kAudioObjectUnknown {
            log("AudioHardwareDestroyAggregateDevice status=\(AudioHardwareDestroyAggregateDevice(aggregateID))")
        }

        aggregateID = kAudioObjectUnknown

        if tapID != kAudioObjectUnknown {
            log("AudioHardwareDestroyProcessTap status=\(AudioHardwareDestroyProcessTap(tapID))")
        }

        tapID = kAudioObjectUnknown

        if let recorder {
            log("Session directory = " + recorder.sessionDirectory.path)
            log("Audio buffers = \(recorder.callbacks)")
            recorder.finish()
        }

        recorder = nil
        activeDeviceUID = nil
    }

    // MARK: select

    // intervalStartWall / intervalEndWall — границы субтитра (epoch-секунды).
    // Если не заданы — работает адаптивный режим от audioReferenceWallClock.
    func select(
        requestID: String,
        word: String,
        audioReferenceWallClock: Double,
        intervalStartWall: Double?,
        intervalEndWall: Double?
    ) {
        guard active else {
            emit("AUDIO_ERROR\t\(requestID)\twatcher_inactive")
            return
        }

        guard let recorder else {
            emit("AUDIO_ERROR\t\(requestID)\trecorder_unavailable")
            return
        }

        log("SELECT received. request=\(requestID) word=\(word)")
        log("reference_wall_time=" + String(format: "%.6f", audioReferenceWallClock))

        var target: Double?
        var endWall: Double?

        if let s = intervalStartWall, let e = intervalEndWall, e > s {
            log(
                "interval_wall = "
                + String(format: "%.6f", s)
                + " -> "
                + String(format: "%.6f", e)
            )

            switch recorder.audioTime(forWall: s, futureTolerance: 0.5) {
            case .ok(let t):
                target = t
                endWall = e
            case .tooOld:
                log("Interval start is older than the ring; falling back to reference time.")
            case .future:
                log("Interval start is ahead of the timeline; falling back to reference time.")
            }
        }

        if target == nil {
            switch recorder.audioTime(
                forWall: audioReferenceWallClock,
                futureTolerance: 0.5
            ) {
            case .ok(let t):
                target = t
                endWall = nil
            case .tooOld:
                log("Reference timestamp is older than the ring buffer.")
            case .future:
                log("Reference timestamp is ahead of the recorder timeline.")
            }
        }

        guard let target else {
            emit("AUDIO_ERROR\t\(requestID)\tinvalid_audio_reference_time")
            return
        }

        log("mapped_audio_time=" + formatTime(target))

        emit("AUDIO_SELECTED\t\(requestID)\t1")

        recorder.select(
            requestID: requestID,
            word: word,
            target: target,
            endWall: endWall
        )
    }

    func status() {
        emit("AUDIO_STATUS\t" + (active ? "on" : "off"))
    }

    func commandStart() {
        commandQueue.async {
            guard !self.active else {
                emit("AUDIO_STATUS\ton")
                return
            }

            self.startReportingErrors()
        }
    }

    func commandStop() {
        commandQueue.sync { self.stop() }
    }

    func commandSelect(
        requestID: String,
        word: String,
        audioReferenceWallClock: Double,
        intervalStartWall: Double?,
        intervalEndWall: Double?
    ) {
        commandQueue.async {
            self.select(
                requestID: requestID,
                word: word,
                audioReferenceWallClock: audioReferenceWallClock,
                intervalStartWall: intervalStartWall,
                intervalEndWall: intervalEndWall
            )
        }
    }

    func commandStatus() {
        commandQueue.async { self.status() }
    }
}


// MARK: - Bridge mode

func connectToSocket(path: String) -> UnixSocket? {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { return nil }

    guard var address = makeSockAddr(path) else {
        close(fd)
        return nil
    }

    let status = withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
            connect(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }

    guard status == 0 else {
        close(fd)
        return nil
    }

    return UnixSocket(fd: fd)
}


func runBridgeMode() {

    let socketPath = Config.socketPath
    let bundlePath = Config.appBundlePath
    let audioDirectory = Config.outputDirectory

    directLog("Bridge mode.")
    directLog("Snap Audio.app = " + bundlePath)
    directLog("Socket = " + socketPath)
    directLog("Audio directory = " + audioDirectory)

    try? FileManager.default.removeItem(atPath: socketPath)

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = [
        "-n",
        bundlePath,
        "--args",
        "--socket", socketPath,
        "--audio-dir", audioDirectory
    ]

    do {
        try process.run()
    } catch {
        directLog("Could not launch Snap Audio.app: " + error.localizedDescription)
        exit(1)
    }

    directLog("Snap Audio.app launch requested.")

    var socket: UnixSocket?

    for _ in 0..<200 {
        if let connected = connectToSocket(path: socketPath) {
            socket = connected
            break
        }

        usleep(50_000)
    }

    guard let socket else {
        directLog("Timed out waiting for Snap Audio.app.")
        exit(1)
    }

    directLog("Connected to Snap Audio.app.")

    let writeSocket = socket

    DispatchQueue.global(qos: .userInitiated).async {
        while let line = readLine() {
            writeSocket.send(line)
        }

        writeSocket.send("EXIT")
    }

    while let line = socket.receiveLine() {
        if line.hasPrefix("LOG\t") {
            print(String(line.dropFirst(4)))
        } else {
            print(line)
        }

        flushStdout()
    }

    exit(0)
}


// MARK: - App mode

func parseWall(_ parts: [String], _ index: Int) -> Double? {
    guard parts.count > index else { return nil }

    let text = parts[index].trimmingCharacters(in: .whitespacesAndNewlines)

    guard !text.isEmpty, let value = Double(text), value.isFinite else { return nil }

    return value
}


func runAppMode() {

    signal(SIGPIPE, SIG_IGN)

    do {
        audioIPCServer = try UnixSocketServer(path: Config.socketPath)
    } catch {
        directLog("IPC error: " + error.localizedDescription)
        exit(1)
    }

    log("Snap Audio.app started.")
    log("Socket = " + Config.socketPath)
    log("Audio backend = Core Audio Process Tap. Tap mode = device-scoped.")
    log("ScreenCaptureKit = disabled. Watcher starts OFF.")
    log("Output directory = " + Config.outputDirectory)

    let capture = SystemAudioCapture()

    if let i = CommandLine.arguments.firstIndex(of: "--parent-pid"),
       i + 1 < CommandLine.arguments.count,
       let parentPID = Int32(CommandLine.arguments[i + 1]) {
        Thread {
            while true {
                sleep(2)
                if kill(parentPID, 0) != 0 && errno == ESRCH {
                    capture.commandStop()
                    audioIPCServer?.closeAll()
                    exit(0)
                }
            }
        }.start()
    }

    DispatchQueue.global(qos: .userInitiated).async {

        guard let client = audioIPCServer?.acceptClient() else {
            log("No IPC client connected.")
            capture.commandStop()
            exit(1)
        }

        log("Python bridge connected.")

        emit("AUDIO_STATUS\toff")

        while let line = client.receiveLine() {

            let parts = line.components(separatedBy: "\t")

            guard let first = parts.first else { continue }

            let command = first
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .uppercased()

            switch command {

            case "TOGGLE":
                log("TOGGLE received.")
                capture.toggle()

            case "START":
                log("START received.")
                capture.commandStart()

            case "STOP":
                log("STOP received.")
                capture.commandStop()

            case "SELECT":
                // SELECT \t id \t word \t refWall [\t startWall \t endWall]
                guard parts.count >= 4 else {
                    emit("AUDIO_ERROR\tsystem\tinvalid_select_command")
                    continue
                }

                guard let reference = parseWall(parts, 3) else {
                    emit("AUDIO_ERROR\t" + parts[1] + "\tinvalid_audio_reference_time")
                    continue
                }

                let intervalStart = parseWall(parts, 4)
                let intervalEnd = parseWall(parts, 5)

                capture.commandSelect(
                    requestID: parts[1],
                    word: parts[2],
                    audioReferenceWallClock: reference,
                    intervalStartWall: intervalStart,
                    intervalEndWall: intervalEnd
                )

            case "STATUS":
                log("STATUS received.")
                capture.commandStatus()

            case "EXIT":
                log("EXIT received.")
                capture.commandStop()
                audioIPCServer?.closeAll()
                exit(0)

            default:
                log("Unknown command: " + command)
            }
        }

        log("IPC client disconnected.")

        capture.commandStop()
        audioIPCServer?.closeAll()

        exit(0)
    }

    RunLoop.main.run()
}


if Config.isAppMode {
    runAppMode()
} else {
    runBridgeMode()
}