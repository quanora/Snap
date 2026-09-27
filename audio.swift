import Foundation
import Darwin
import CoreGraphics
import CoreMedia
import CoreVideo
import AVFoundation
import ScreenCaptureKit
import Vision
import AppKit
import ApplicationServices

enum Config {

```
// MARK: - Screen

static let fps = 10

static let captureWidth = 768
static let captureHeight = 497

static let roiX = 0.02
static let roiY = 0.02
static let roiWidth = 0.96
static let roiHeight = 0.90


// MARK: - Vision

static let minimumConfidence: Float = 0.20
static let minimumTextHeight: Float = 0.006

static let minimumWidth = 0.012
static let maximumHeight = 0.16
static let minimumCharacters = 2


// MARK: - Subtitle timing

static let disappearedFrames = 4

static let appearedConfirmations = 2
static let changedConfirmations = 2

static let sameTextThreshold = 0.85
static let pendingTextThreshold = 0.72
static let samePositionThreshold = 0.55


// OCR correction protection.

static let ocrRevisionPosition = 0.55
static let ocrRevisionSimilarity = 0.68
static let ocrRevisionMinimumCommonWords = 3


// Audio boundaries.

// Небольшой запас перед первым обнаружением subtitle.
static let subtitleStartPadding = 0.50

// Небольшой запас после последнего обнаружения subtitle.
static let subtitleEndPadding = 0.15


// MARK: - Debug

static let debugInterval = 2.0


// MARK: - Audio

static let audioSampleRate = 48000
static let audioChannelCount = 2
static let audioBitrate = 192000


// Храним последние N секунд аудио
// для мгновенного создания clip.
static let audioRingBufferSeconds = 60.0


// MARK: - Silence

static let silenceDuration = 1.0
static let silenceThreshold = "-35dB"


// MARK: - Output

static let audioOutputDirectory =
    NSHomeDirectory()
    + "/Downloads/SnapAudioTest"


// MARK: - Test hotkey

static let selectionKey = "x"
```

}

struct RuntimeError:
Error,
LocalizedError
{
let message: String

```
init(_ message: String) {
    self.message = message
}

var errorDescription: String? {
    return message
}
```

}

struct SubtitleCandidate {

```
let text: String

let x: Double
let y: Double
let width: Double
let height: Double

let confidence: Float

let pts: Double

var centerX: Double {
    return x + width / 2.0
}

var centerY: Double {
    return y + height / 2.0
}
```

}

struct WordSelection:
Codable
{
let word: String
let selectedPTS: Double
}

struct SubtitleSegment:
Codable
{
let id: Int
let text: String
let startPTS: Double
let endPTS: Double
let selections: [WordSelection]

```
var duration: Double {
    return max(
        0.0,
        endPTS - startPTS
    )
}
```

}

struct AudioClipResult:
Codable
{
let id: Int
let text: String
let selections: [WordSelection]

```
let rawFile: String
let trimmedFile: String

let success: Bool
```

}

struct AudioChunk {

```
let sampleBuffer: CMSampleBuffer

let startPTS: Double
let endPTS: Double
```

}

final class AudioRecorder {

```
let sessionDirectory:
    URL

let masterURL:
    URL


private let audioQueue:
    DispatchQueue

private let exportQueue:
    DispatchQueue


// MARK: - Master writer

private var masterWriter:
    AVAssetWriter?

private var masterInput:
    AVAssetWriterInput?

private var masterStarted =
    false


// MARK: - Ring buffer

private var ringBuffer:
    [AudioChunk] = []


// MARK: - Statistics

private var bufferCount =
    0

private var droppedBuffers =
    0

private var firstAudioPTS:
    Double?


// MARK: - Export state

private var exportedIDs:
    Set<Int> = []

private var deferredSegments:
    [SubtitleSegment] = []

private var results:
    [AudioClipResult] = []


init(
    baseDirectory:
        String,
    audioQueue:
        DispatchQueue
) throws {

    self.audioQueue =
        audioQueue

    self.exportQueue =
        DispatchQueue(
            label:
                "snap.audio.export",
            qos:
                .utility
        )


    let baseURL =
        URL(
            fileURLWithPath:
                baseDirectory
        )


    try FileManager.default
        .createDirectory(
            at:
                baseURL,
            withIntermediateDirectories:
                true
        )


    let formatter =
        DateFormatter()

    formatter.dateFormat =
        "yyyy-MM-dd_HH-mm-ss"


    let sessionName =
        "session_"
        + formatter.string(
            from:
                Date()
        )


    sessionDirectory =
        baseURL
            .appendingPathComponent(
                sessionName
            )


    try FileManager.default
        .createDirectory(
            at:
                sessionDirectory,
            withIntermediateDirectories:
                true
        )


    masterURL =
        sessionDirectory
            .appendingPathComponent(
                "master.m4a"
            )
}


var audioBufferCount:
    Int
{
    return audioQueue.sync {
        bufferCount
    }
}


var droppedAudioBuffers:
    Int
{
    return audioQueue.sync {
        droppedBuffers
    }
}


// MARK: - Continuous recording

func append(
    _ sampleBuffer:
        CMSampleBuffer
) {

    guard sampleBuffer.isValid else {
        return
    }


    guard CMSampleBufferDataIsReady(
        sampleBuffer
    )
    else {
        return
    }


    let pts =
        CMTimeGetSeconds(
            CMSampleBufferGetPresentationTimeStamp(
                sampleBuffer
            )
        )


    let durationTime =
        CMSampleBufferGetDuration(
            sampleBuffer
        )


    let duration =
        durationTime.isValid
        && !durationTime.isIndefinite
        ? CMTimeGetSeconds(
            durationTime
        )
        : 0.02


    let endPTS =
        pts
        + max(
            0.001,
            duration
        )


    if firstAudioPTS == nil {

        firstAudioPTS =
            pts


        print(
            ""
        )

        print(
            "First audio PTS: "
            + format(
                pts
            )
        )
    }


    if masterWriter == nil {

        do {

            try createMasterWriter(
                sampleBuffer
            )

        } catch {

            print(
                "Audio writer ERROR: "
                + error.localizedDescription
            )

            return
        }
    }


    appendToMaster(
        sampleBuffer
    )


    ringBuffer.append(
        AudioChunk(
            sampleBuffer:
                sampleBuffer,
            startPTS:
                pts,
            endPTS:
                endPTS
        )
    )


    let cutoff =
        endPTS
        - Config.audioRingBufferSeconds


    while let first =
        ringBuffer.first
    {

        if first.endPTS <
            cutoff
        {
            ringBuffer.removeFirst()
        } else {
            break
        }
    }
}


private func createMasterWriter(
    _ sampleBuffer:
        CMSampleBuffer
) throws {

    guard let formatDescription =
        CMSampleBufferGetFormatDescription(
            sampleBuffer
        )
    else {
        throw RuntimeError(
            "Could not get audio format description"
        )
    }


    let writer =
        try AVAssetWriter(
            outputURL:
                masterURL,
            fileType:
                .m4a
        )


    let settings:
        [String: Any] =
    [
        AVFormatIDKey:
            kAudioFormatMPEG4AAC,

        AVSampleRateKey:
            Config.audioSampleRate,

        AVNumberOfChannelsKey:
            Config.audioChannelCount,

        AVEncoderBitRateKey:
            Config.audioBitrate
    ]


    let input =
        AVAssetWriterInput(
            mediaType:
                .audio,
            outputSettings:
                settings,
            sourceFormatHint:
                formatDescription
        )


    input.expectsMediaDataInRealTime =
        true


    guard writer.canAdd(
        input
    )
    else {
        throw RuntimeError(
            "Could not add master audio input"
        )
    }


    writer.add(
        input
    )


    masterWriter =
        writer

    masterInput =
        input
}


private func appendToMaster(
    _ sampleBuffer:
        CMSampleBuffer
) {

    guard let masterWriter,
          let masterInput
    else {
        return
    }


    if !masterStarted {

        guard masterWriter.startWriting()
        else {

            print(
                "Master audio writer ERROR: "
                + (
                    masterWriter.error?
                        .localizedDescription
                    ?? "unknown error"
                )
            )

            return
        }


        masterWriter.startSession(
            atSourceTime:
                CMSampleBufferGetPresentationTimeStamp(
                    sampleBuffer
                )
        )


        masterStarted =
            true


        print("")
        print(
            "Continuous audio recording started."
        )

        print(
            "Master:"
        )

        print(
            masterURL.path
        )

        print("")
    }


    guard masterInput.isReadyForMoreMediaData
    else {

        droppedBuffers +=
            1

        return
    }


    if masterInput.append(
        sampleBuffer
    ) {

        bufferCount +=
            1

    } else {

        print(
            "Master audio append ERROR: "
            + (
                masterWriter.error?
                    .localizedDescription
                ?? "unknown error"
            )
        )
    }


    if bufferCount % 200 == 0 {

        print(
            "Audio buffers: "
            + "\(bufferCount)"
        )
    }
}


// MARK: - Live segment export

func exportSegment(
    _ segment:
        SubtitleSegment
) {

    exportQueue.async {

        self.exportSegmentNow(
            segment
        )
    }
}


private func exportSegmentNow(
    _ segment:
        SubtitleSegment
) {

    guard !segment.selections.isEmpty
    else {
        return
    }


    if exportedIDs.contains(
        segment.id
    )
    {
        return
    }


    let snapshot:
        [AudioChunk]

    let oldestPTS:
        Double?


    (
        snapshot,
        oldestPTS
    ) =
        audioQueue.sync {

            return (
                self.ringBuffer,
                self.ringBuffer.first?.startPTS
            )
        }


    guard let oldestPTS
    else {

        print(
            "Audio segment #"
            + "\(segment.id)"
            + " deferred: ring buffer empty."
        )


        deferredSegments.append(
            segment
        )

        return
    }


    if segment.startPTS <
        oldestPTS
    {

        print(
            "Audio segment #"
            + "\(segment.id)"
            + " deferred: subtitle is older than ring buffer."
        )


        deferredSegments.append(
            segment
        )

        return
    }


    do {

        let result =
            try writeSegmentFromChunks(
                segment,
                chunks:
                    snapshot
            )


        exportedIDs.insert(
            segment.id
        )


        results.append(
            result
        )


    } catch {

        print("")
        print(
            "Live audio export ERROR for segment #"
            + "\(segment.id)"
        )

        print(
            error.localizedDescription
        )

        print("")
    }
}


private func writeSegmentFromChunks(
    _ segment:
        SubtitleSegment,
    chunks:
        [AudioChunk]
) throws
    -> AudioClipResult
{

    guard let firstChunk =
        chunks.first(
            where:
            {
                $0.endPTS
                    >= segment.startPTS
                &&
                $0.startPTS
                    <= segment.endPTS
            }
        )
    else {

        throw RuntimeError(
            "No audio samples overlap segment"
        )
    }


    let selectedChunks =
        chunks.filter {
            $0.endPTS >= segment.startPTS
            &&
            $0.startPTS <= segment.endPTS
        }


    guard !selectedChunks.isEmpty
    else {
        throw RuntimeError(
            "No audio chunks selected"
        )
    }


    let rawURL =
        makeRawSegmentURL(
            id:
                segment.id
        )


    let trimmedURL =
        makeTrimmedSegmentURL(
            id:
                segment.id
        )


    let actualStartPTS =
        firstChunk.startPTS


    try writeRawAudio(
        chunks:
            selectedChunks,
        output:
            rawURL
    )


    let trimStart =
        max(
            0.0,
            segment.startPTS
            - actualStartPTS
        )


    let requestedDuration =
        max(
            0.05,
            segment.endPTS
            - segment.startPTS
        )


    try trimSilence(
        input:
            rawURL,
        output:
            trimmedURL,
        start:
            trimStart,
        duration:
            requestedDuration
    )


    print("")
    print(
        "Audio segment exported:"
    )


    print(
        "  #"
        + "\(segment.id)"
    )


    print(
        "  text="
        + segment.text
    )


    print(
        "  selections="
        + segment.selections
            .map {
                $0.word
            }
            .joined(
                separator:
                    ", "
            )
    )


    print(
        "  raw="
        + rawURL.path
    )


    print(
        "  trimmed="
        + trimmedURL.path
    )


    print("")


    return AudioClipResult(
        id:
            segment.id,
        text:
            segment.text,
        selections:
            segment.selections,
        rawFile:
            rawURL.lastPathComponent,
        trimmedFile:
            trimmedURL.lastPathComponent,
        success:
            true
    )
}


private func writeRawAudio(
    chunks:
        [AudioChunk],
    output:
        URL
) throws {

    guard let first =
        chunks.first
    else {
        throw RuntimeError(
            "No chunks available"
        )
    }


    guard let formatDescription =
        CMSampleBufferGetFormatDescription(
            first.sampleBuffer
        )
    else {
        throw RuntimeError(
            "Could not get audio format description"
        )
    }


    if FileManager.default
        .fileExists(
            atPath:
                output.path
        )
    {

        try FileManager.default
            .removeItem(
                at:
                    output
            )
    }


    let writer =
        try AVAssetWriter(
            outputURL:
                output,
            fileType:
                .m4a
        )


    let settings:
        [String: Any] =
    [
        AVFormatIDKey:
            kAudioFormatMPEG4AAC,

        AVSampleRateKey:
            Config.audioSampleRate,

        AVNumberOfChannelsKey:
            Config.audioChannelCount,

        AVEncoderBitRateKey:
            Config.audioBitrate
    ]


    let input =
        AVAssetWriterInput(
            mediaType:
                .audio,
            outputSettings:
                settings,
            sourceFormatHint:
                formatDescription
        )


    input.expectsMediaDataInRealTime =
        false


    guard writer.canAdd(
        input
    )
    else {
        throw RuntimeError(
            "Could not add segment audio input"
        )
    }


    writer.add(
        input
    )


    guard writer.startWriting()
    else {
        throw RuntimeError(
            "Could not start segment writer: "
            + (
                writer.error?
                    .localizedDescription
                ?? "unknown error"
            )
        )
    }


    writer.startSession(
        atSourceTime:
            CMSampleBufferGetPresentationTimeStamp(
                first.sampleBuffer
            )
    )


    for chunk in
        chunks
    {

        guard writer.status ==
            .writing
        else {
            break
        }


        if input.isReadyForMoreMediaData {

            guard input.append(
                chunk.sampleBuffer
            )
            else {

                throw RuntimeError(
                    "Could not append segment audio"
                )
            }
        }
    }


    input.markAsFinished()


    let semaphore =
        DispatchSemaphore(
            value:
                0
        )


    writer.finishWriting {

        semaphore.signal()
    }


    semaphore.wait()


    guard writer.status ==
        .completed
    else {

        throw RuntimeError(
            "Segment writer failed: "
            + (
                writer.error?
                    .localizedDescription
                ?? "unknown error"
            )
        )
    }
}


// MARK: - Deferred export from master

func exportDeferredSegments() {

    exportQueue.sync {

        guard !deferredSegments.isEmpty
        else {
            return
        }


        guard let firstAudioPTS
        else {

            print(
                "Cannot export deferred segments: no audio PTS."
            )

            return
        }


        print("")
        print(
            "Exporting deferred segments from master..."
        )

        print("")


        let segments =
            deferredSegments


        for segment in
            segments
        {

            if exportedIDs.contains(
                segment.id
            )
            {
                continue
            }


            do {

                let result =
                    try exportFromMaster(
                        segment,
                        firstAudioPTS:
                            firstAudioPTS
                    )


                exportedIDs.insert(
                    segment.id
                )


                results.append(
                    result
                )

            } catch {

                print(
                    "Deferred export ERROR for segment #"
                    + "\(segment.id)"
                )

                print(
                    error.localizedDescription
                )

                print("")
            }
        }
    }
}


private func exportFromMaster(
    _ segment:
        SubtitleSegment,
    firstAudioPTS:
        Double
) throws
    -> AudioClipResult
{

    let rawURL =
        makeRawSegmentURL(
            id:
                segment.id
        )


    let trimmedURL =
        makeTrimmedSegmentURL(
            id:
                segment.id
        )


    let start =
        max(
            0.0,
            segment.startPTS
            - firstAudioPTS
        )


    let duration =
        max(
            0.05,
            segment.endPTS
            - segment.startPTS
        )


    let ffmpeg =
        findFFmpeg()


    guard let ffmpeg
    else {
        throw RuntimeError(
            "ffmpeg not found"
        )
    }


    try extractFromMaster(
        ffmpeg:
            ffmpeg,
        output:
            rawURL,
        start:
            start,
        duration:
            duration
    )


    try trimSilence(
        input:
            rawURL,
        output:
            trimmedURL,
        start:
            0.0,
        duration:
            duration
    )


    print("")
    print(
        "Deferred audio segment exported:"
    )


    print(
        "  #"
        + "\(segment.id)"
    )


    print(
        "  raw="
        + rawURL.path
    )


    print(
        "  trimmed="
        + trimmedURL.path
    )


    print("")


    return AudioClipResult(
        id:
            segment.id,
        text:
            segment.text,
        selections:
            segment.selections,
        rawFile:
            rawURL.lastPathComponent,
        trimmedFile:
            trimmedURL.lastPathComponent,
        success:
            true
    )
}


private func extractFromMaster(
    ffmpeg:
        String,
    output:
        URL,
    start:
        Double,
    duration:
        Double
) throws {

    let process =
        Process()


    process.executableURL =
        URL(
            fileURLWithPath:
                ffmpeg
        )


    process.arguments =
    [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",

        "-i",
        masterURL.path,

        "-ss",
        formatFFmpegTime(
            start
        ),

        "-t",
        formatFFmpegTime(
            duration
        ),

        "-vn",

        "-c:a",
        "aac",

        "-b:a",
        "\(Config.audioBitrate)",

        output.path
    ]


    let errorPipe =
        Pipe()


    process.standardError =
        errorPipe


    try process.run()

    process.waitUntilExit()


    guard process.terminationStatus ==
        0
    else {

        let data =
            errorPipe
                .fileHandleForReading
                .readDataToEndOfFile()


        let message =
            String(
                data:
                    data,
                encoding:
                    .utf8
            )
            ?? "unknown ffmpeg error"


        throw RuntimeError(
            message
        )
    }
}


// MARK: - Silence trimming

private func trimSilence(
    input:
        URL,
    output:
        URL,
    start:
        Double,
    duration:
        Double
) throws {

    let ffmpeg =
        findFFmpeg()


    guard let ffmpeg
    else {
        throw RuntimeError(
            "ffmpeg not found"
        )
    }


    let filter =
        "silenceremove="
        + "start_periods=1:"
        + "start_threshold="
        + Config.silenceThreshold
        + ":"
        + "stop_periods=-1:"
        + "stop_duration="
        + String(
            Config.silenceDuration
        )
        + ":"
        + "stop_threshold="
        + Config.silenceThreshold


    let process =
        Process()


    process.executableURL =
        URL(
            fileURLWithPath:
                ffmpeg
        )


    process.arguments =
    [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",

        "-i",
        input.path,

        "-ss",
        formatFFmpegTime(
            start
        ),

        "-t",
        formatFFmpegTime(
            duration
        ),

        "-af",
        filter,

        "-c:a",
        "aac",

        "-b:a",
        "\(Config.audioBitrate)",

        output.path
    ]


    let errorPipe =
        Pipe()


    process.standardError =
        errorPipe


    try process.run()

    process.waitUntilExit()


    guard process.terminationStatus ==
        0
    else {

        let data =
            errorPipe
                .fileHandleForReading
                .readDataToEndOfFile()


        let message =
            String(
                data:
                    data,
                encoding:
                    .utf8
            )
            ?? "unknown ffmpeg error"


        throw RuntimeError(
            message
        )
    }
}


// MARK: - Finish master

func finishMaster() {

    guard masterStarted,
          let masterWriter,
          let masterInput
    else {
        return
    }


    masterInput.markAsFinished()


    let semaphore =
        DispatchSemaphore(
            value:
                0
        )


    masterWriter.finishWriting {

        semaphore.signal()
    }


    semaphore.wait()


    if masterWriter.status ==
        .failed
    {

        print(
            "Master writer ERROR: "
            + (
                masterWriter.error?
                    .localizedDescription
                ?? "unknown error"
            )
        )

    } else {

        print("")
        print(
            "Master audio finished:"
        )

        print(
            masterURL.path
        )

        print("")
    }
}


// MARK: - Export queue

func waitForExports() {

    exportQueue.sync {}
}


// MARK: - Results

func exportResults()
    -> [AudioClipResult]
{

    return exportQueue.sync {
        results
    }
}


// MARK: - Paths

private func makeRawSegmentURL(
    id:
        Int
) -> URL {

    return sessionDirectory
        .appendingPathComponent(
            String(
                format:
                    "clip_%03d.m4a",
                id
            )
        )
}


private func makeTrimmedSegmentURL(
    id:
        Int
) -> URL {

    return sessionDirectory
        .appendingPathComponent(
            String(
                format:
                    "clip_%03d.trimmed.m4a",
                id
            )
        )
}


private func findFFmpeg()
    -> String?
{

    let paths =
    [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg"
    ]


    for path in
        paths
    {

        if FileManager.default
            .fileExists(
                atPath:
                    path
            )
        {
            return path
        }
    }


    return nil
}


private func format(
    _ value:
        Double
) -> String {

    return String(
        format:
            "%.3f",
        value
    )
}


private func formatFFmpegTime(
    _ value:
        Double
) -> String {

    return String(
        format:
            "%.3f",
        value
    )
}
```

}

// MARK: - Subtitle Detector

final class SubtitleDetector:
NSObject,
SCStreamOutput,
SCStreamDelegate
{

```
private var stream:
    SCStream?


private var audioRecorder:
    AudioRecorder?


private let processingQueue =
    DispatchQueue(
        label:
            "snap.subtitle.detector",
        qos:
            .userInitiated
    )


private let audioQueue =
    DispatchQueue(
        label:
            "snap.audio.recorder",
        qos:
            .userInitiated
    )


// MARK: - Subtitle state

private var subtitleActive =
    false

private var currentSubtitle:
    SubtitleCandidate?

private var currentSubtitleStartPTS:
    Double?

private var lastSubtitleSeenPTS:
    Double?


private var pendingSubtitle:
    SubtitleCandidate?

private var pendingCount =
    0

private var pendingFirstPTS:
    Double?


private var missingFrames =
    0


// MARK: - Segment state

private var currentSegmentID =
    1

private var currentSelections:
    [WordSelection] = []

private var completedSegments:
    [SubtitleSegment] = []


// MARK: - Timing

private var lastScreenPTS:
    Double?

private var screenFrameCount =
    0


// MARK: - Vision statistics

private var frameCount =
    0

private var visionCount =
    0

private var totalVisionTime:
    Double = 0

private var lastDebugTime =
    CFAbsoluteTimeGetCurrent()

private var lastCandidate:
    SubtitleCandidate?


// MARK: - Stop

private var stopping =
    false


// MARK: - Vision request

private lazy var textRequest:
    VNRecognizeTextRequest =
{

    let request =
        VNRecognizeTextRequest()


    request.recognitionLevel =
        .fast

    request.usesLanguageCorrection =
        false

    request.automaticallyDetectsLanguage =
        true

    request.minimumTextHeight =
        Config.minimumTextHeight

    request.regionOfInterest =
        CGRect(
            x:
                Config.roiX,
            y:
                Config.roiY,
            width:
                Config.roiWidth,
            height:
                Config.roiHeight
        )


    return request
}()


// MARK: - Start

func start() async throws {

    audioRecorder =
        try AudioRecorder(
            baseDirectory:
                Config.audioOutputDirectory,
            audioQueue:
                audioQueue
        )


    let content =
        try await SCShareableContent
            .excludingDesktopWindows(
                false,
                onScreenWindowsOnly:
                    true
            )


    let mainDisplayID =
        CGMainDisplayID()


    if let display =
        content.displays.first(
            where:
            {
                $0.displayID ==
                    mainDisplayID
            }
        )
    {

        try await start(
            display
        )

        return
    }


    guard let display =
        content.displays.first
    else {

        throw RuntimeError(
            "No display found"
        )
    }


    try await start(
        display
    )
}


private func start(
    _ display:
        SCDisplay
) async throws {

    print("")
    print(
        "Snap Subtitle + Audio Watch"
    )


    print(
        "Display: "
        + "\(Int(display.frame.width))x"
        + "\(Int(display.frame.height))"
    )


    print(
        "Capture: "
        + "\(Config.captureWidth)x"
        + "\(Config.captureHeight)"
    )


    print(
        "FPS: "
        + "\(Config.fps)"
    )


    print(
        "Vision: text recognition"
    )


    print(
        "Subtitle tracking: temporal"
    )


    print(
        "Audio: continuous + rolling buffer"
    )


    print(
        "Audio buffer:"
        + " "
        + "\(Int(Config.audioRingBufferSeconds)) s"
    )


    print(
        "Selection hotkey:"
        + " "
        + Config.selectionKey.uppercased()
    )


    print(
        "Silence removal:"
        + " "
        + "\(Config.silenceDuration)"
        + " s / "
        + Config.silenceThreshold
    )


    if let audioRecorder {

        print("")
        print(
            "Session directory:"
        )

        print(
            audioRecorder.sessionDirectory.path
        )
    }


    print("")


    warmUpVision(
        displayID:
            display.displayID
    )


    let filter =
        SCContentFilter(
            display:
                display,
            excludingWindows:
                []
        )


    let configuration =
        SCStreamConfiguration()


    configuration.width =
        Config.captureWidth

    configuration.height =
        Config.captureHeight

    configuration.preservesAspectRatio =
        true


    configuration.minimumFrameInterval =
        CMTime(
            value:
                1,
            timescale:
                CMTimeScale(
                    Config.fps
                )
        )


    configuration.pixelFormat =
        kCVPixelFormatType_32BGRA


    configuration.queueDepth =
        2


    configuration.showsCursor =
        false


    // Audio.

    configuration.capturesAudio =
        true

    configuration.sampleRate =
        Config.audioSampleRate

    configuration.channelCount =
        Config.audioChannelCount

    configuration.excludesCurrentProcessAudio =
        true


    let newStream =
        SCStream(
            filter:
                filter,
            configuration:
                configuration,
            delegate:
                self
        )


    try newStream.addStreamOutput(
        self,
        type:
            .screen,
        sampleHandlerQueue:
            processingQueue
    )


    try newStream.addStreamOutput(
        self,
        type:
            .audio,
        sampleHandlerQueue:
            audioQueue
    )


    stream =
        newStream


    try await newStream.startCapture()


    print("")
    print(
        "Capture started."
    )


    print(
        "Screen + system audio are being captured continuously."
    )


    print("")
    print(
        "Press X when you select a word."
    )


    print(
        "X is currently a test selection."
    )


    print(
        "The real Snap project can call:"
    )


    print(
        "selectWord(\"word\")"
    )


    print("")


    print(
        "Press Ctrl+C to stop."
    )


    print("")
}


// MARK: - Vision warmup

private func warmUpVision(
    displayID:
        CGDirectDisplayID
) {

    guard let image =
        CGDisplayCreateImage(
            displayID
        )
    else {
        return
    }


    let start =
        CFAbsoluteTimeGetCurrent()


    let handler =
        VNImageRequestHandler(
            cgImage:
                image,
            orientation:
                .up,
            options:
                [:]
        )


    do {

        try handler.perform(
            [
                textRequest
            ]
        )

    } catch {

        print(
            "Vision warmup failed: "
            + error.localizedDescription
        )

        return
    }


    let elapsed =
        CFAbsoluteTimeGetCurrent()
        - start


    print(
        "Vision warmup: "
        + format(
            elapsed * 1000.0
        )
        + " ms"
    )
}


// MARK: - ScreenCaptureKit callback

func stream(
    _ stream:
        SCStream,
    didOutputSampleBuffer sampleBuffer:
        CMSampleBuffer,
    of type:
        SCStreamOutputType
) {

    guard sampleBuffer.isValid else {
        return
    }


    switch type {

    case .screen:

        handleScreen(
            sampleBuffer
        )


    case .audio:

        guard !stopping else {
            return
        }


        audioRecorder?.append(
            sampleBuffer
        )


    default:

        return
    }
}


// MARK: - Screen

private func handleScreen(
    _ sampleBuffer:
        CMSampleBuffer
) {

    guard isUsableScreenFrame(
        sampleBuffer
    )
    else {
        // В том числе SCFrameStatus.idle.
        // При паузе видео состояние subtitle
        // намеренно не меняем.
        return
    }


    guard let pixelBuffer =
        CMSampleBufferGetImageBuffer(
            sampleBuffer
        )
    else {
        return
    }


    let pts =
        CMTimeGetSeconds(
            CMSampleBufferGetPresentationTimeStamp(
                sampleBuffer
            )
        )


    lastScreenPTS =
        pts


    screenFrameCount +=
        1


    let start =
        CFAbsoluteTimeGetCurrent()


    let candidate =
        detectSubtitle(
            pixelBuffer,
            pts:
                pts
        )


    lastCandidate =
        candidate


    processCandidate(
        candidate,
        pts:
            pts
    )


    let elapsed =
        CFAbsoluteTimeGetCurrent()
        - start


    totalVisionTime +=
        elapsed


    visionCount +=
        1

    frameCount +=
        1


    printDebugIfNeeded()
}


private func isUsableScreenFrame(
    _ sampleBuffer:
        CMSampleBuffer
) -> Bool {

    guard let attachmentsArray =
        CMSampleBufferGetSampleAttachmentsArray(
            sampleBuffer,
            createIfNecessary:
                false
        )
        as? [[SCStreamFrameInfo: Any]]
    else {
        return true
    }


    guard let attachments =
        attachmentsArray.first
    else {
        return true
    }


    guard let rawValue =
        attachments[
            SCStreamFrameInfo.status
        ]
        as? Int
    else {
        return true
    }


    guard let status =
        SCFrameStatus(
            rawValue:
                rawValue
        )
    else {
        return true
    }


    switch status {

    case .idle:
        return false

    case .suspended:
        return false

    case .stopped:
        return false

    case .complete:
        return true

    case .started:
        return true

    case .blank:
        return true

    default:
        return true
    }
}


// MARK: - Vision

private func detectSubtitle(
    _ pixelBuffer:
        CVPixelBuffer,
    pts:
        Double
) -> SubtitleCandidate?
{

    let handler =
        VNImageRequestHandler(
            cvPixelBuffer:
                pixelBuffer,
            orientation:
                .up,
            options:
                [:]
        )


    do {

        try handler.perform(
            [
                textRequest
            ]
        )

    } catch {

        return nil
    }


    guard let observations =
        textRequest.results
    else {
        return nil
    }


    var candidates:
        [SubtitleCandidate] = []


    for observation in
        observations
    {

        guard let topCandidate =
            observation
                .topCandidates(1)
                .first
        else {
            continue
        }


        let text =
            normalizeText(
                topCandidate.string
            )


        guard text.count
            >= Config.minimumCharacters
        else {
            continue
        }


        let confidence =
            topCandidate.confidence


        guard confidence
            >= Config.minimumConfidence
        else {
            continue
        }


        let box =
            observation.boundingBox


        guard box.width
            >= Config.minimumWidth
        else {
            continue
        }


        guard box.height
            <= Config.maximumHeight
        else {
            continue
        }


        let centerY =
            box.midY


        guard centerY >= 0.03,
              centerY <= 0.90
        else {
            continue
        }


        candidates.append(
            SubtitleCandidate(
                text:
                    text,
                x:
                    box.minX,
                y:
                    box.minY,
                width:
                    box.width,
                height:
                    box.height,
                confidence:
                    confidence,
                pts:
                    pts
            )
        )
    }


    guard !candidates.isEmpty
    else {
        return nil
    }


    return selectBestCandidate(
        candidates
    )
}


private func selectBestCandidate(
    _ candidates:
        [SubtitleCandidate]
) -> SubtitleCandidate?
{

    var best:
        SubtitleCandidate?


    var bestScore =
        -Double.infinity


    for candidate in
        candidates
    {

        var score =
            0.0


        let widthScore =
            min(
                1.0,
                candidate.width / 0.60
            )


        let characterScore =
            min(
                1.0,
                Double(
                    candidate.text.count
                ) / 40.0
            )


        let subtitlePositionScore =
            positionScore(
                candidate
            )


        score +=
            widthScore * 2.0


        score +=
            characterScore


        score +=
            subtitlePositionScore * 1.5


        if let currentSubtitle {

            score +=
                textSimilarity(
                    currentSubtitle.text,
                    candidate.text
                ) * 4.0


            score +=
                positionSimilarity(
                    currentSubtitle,
                    candidate
                ) * 3.0
        }


        if let best {

            let similarity =
                textSimilarity(
                    best.text,
                    candidate.text
                )


            if similarity >= 0.90 {

                score +=
                    1.5
            }
        }


        if score >
            bestScore
        {

            bestScore =
                score

            best =
                candidate
        }
    }


    return best
}


private func positionScore(
    _ candidate:
        SubtitleCandidate
) -> Double {

    let centerY =
        candidate.centerY


    let distance =
        abs(
            centerY - 0.22
        )


    let yScore =
        max(
            0.0,
            1.0 - distance / 0.65
        )


    let centerDistance =
        abs(
            candidate.centerX - 0.5
        )


    let xScore =
        max(
            0.0,
            1.0 - centerDistance / 0.5
        )


    return (
        yScore * 0.65
        + xScore * 0.35
    )
}


private func positionSimilarity(
    _ a:
        SubtitleCandidate,
    _ b:
        SubtitleCandidate
) -> Double {

    let centerDistanceX =
        abs(
            a.centerX - b.centerX
        )


    let centerDistanceY =
        abs(
            a.centerY - b.centerY
        )


    let widthDifference =
        abs(
            a.width - b.width
        )


    let heightDifference =
        abs(
            a.height - b.height
        )


    let xScore =
        max(
            0.0,
            1.0 - centerDistanceX / 0.45
        )


    let yScore =
        max(
            0.0,
            1.0 - centerDistanceY / 0.15
        )


    let widthScore =
        max(
            0.0,
            1.0 - widthDifference / 0.50
        )


    let heightScore =
        max(
            0.0,
            1.0 - heightDifference / 0.12
        )


    return (
        xScore * 0.30
        + yScore * 0.40
        + widthScore * 0.20
        + heightScore * 0.10
    )
}


// MARK: - Subtitle state machine

private func processCandidate(
    _ candidate:
        SubtitleCandidate?,
    pts:
        Double
) {

    guard let candidate
    else {

        missingFrames +=
            1


        pendingSubtitle =
            nil

        pendingCount =
            0

        pendingFirstPTS =
            nil


        if subtitleActive,
           missingFrames
                >= Config.disappearedFrames
        {

            let endPTS =
                (
                    lastSubtitleSeenPTS
                    ?? pts
                )
                + Config.subtitleEndPadding


            closeCurrentSubtitle(
                at:
                    endPTS
            )


            print("")
            print(
                "SUBTITLE_DISAPPEARED"
            )


            print(
                "  pts="
                + format(
                    endPTS
                )
            )


            print("")


            subtitleActive =
                false

            currentSubtitle =
                nil

            currentSubtitleStartPTS =
                nil

            lastSubtitleSeenPTS =
                nil

            missingFrames =
                0
        }


        return
    }


    missingFrames =
        0


    if !subtitleActive {

        processAppearance(
            candidate
        )

        return
    }


    processActiveSubtitle(
        candidate
    )
}


// MARK: - Appearance

private func processAppearance(
    _ candidate:
        SubtitleCandidate
) {

    guard let pendingSubtitle
    else {

        self.pendingSubtitle =
            candidate

        pendingCount =
            1

        pendingFirstPTS =
            candidate.pts

        return
    }


    let similarity =
        textSimilarity(
            pendingSubtitle.text,
            candidate.text
        )


    let position =
        positionSimilarity(
            pendingSubtitle,
            candidate
        )


    if similarity
        >= Config.pendingTextThreshold
        && position
            >= 0.35
    {

        pendingCount +=
            1

    } else {

        self.pendingSubtitle =
            candidate

        pendingCount =
            1

        pendingFirstPTS =
            candidate.pts
    }


    if pendingCount
        >= Config.appearedConfirmations
    {

        let firstPTS =
            pendingFirstPTS
            ?? candidate.pts


        subtitleActive =
            true


        currentSubtitle =
            candidate


        currentSubtitleStartPTS =
            firstPTS
            - Config.subtitleStartPadding


        lastSubtitleSeenPTS =
            candidate.pts


        self.pendingSubtitle =
            nil

        pendingCount =
            0

        pendingFirstPTS =
            nil


        currentSelections =
            []


        print("")
        print(
            "SUBTITLE_APPEARED"
        )


        printCandidate(
            candidate
        )


        print(
            "  segment="
            + "\(currentSegmentID)"
        )


        print(
            "  audio_start="
            + format(
                currentSubtitleStartPTS
                ?? firstPTS
            )
        )


        print("")


        // Никакой записи здесь не запускается.
        // AudioRecorder уже пишет непрерывно.
    }
}


// MARK: - Active subtitle

private func processActiveSubtitle(
    _ candidate:
        SubtitleCandidate
) {

    guard let currentSubtitle
    else {

        startNewSubtitle(
            candidate,
            firstPTS:
                candidate.pts
        )

        return
    }


    let similarity =
        textSimilarity(
            currentSubtitle.text,
            candidate.text
        )


    let position =
        positionSimilarity(
            currentSubtitle,
            candidate
        )


    // Тот же subtitle.

    if similarity
        >= Config.sameTextThreshold
        ||
        (
            similarity >= 0.72
            &&
            position
                >= Config.samePositionThreshold
        )
    {

        self.currentSubtitle =
            candidate

        lastSubtitleSeenPTS =
            candidate.pts

        pendingSubtitle =
            nil

        pendingCount =
            0

        pendingFirstPTS =
            nil

        return
    }


    // Постепенное исправление OCR.

    if isLikelyOCRRevision(
        currentSubtitle.text,
        candidate.text,
        position
    )
    {

        self.currentSubtitle =
            candidate

        lastSubtitleSeenPTS =
            candidate.pts

        pendingSubtitle =
            nil

        pendingCount =
            0

        pendingFirstPTS =
            nil

        return
    }


    // Возможный новый subtitle.

    guard let pendingSubtitle
    else {

        self.pendingSubtitle =
            candidate

        pendingCount =
            1

        pendingFirstPTS =
            candidate.pts

        return
    }


    let pendingSimilarity =
        textSimilarity(
            pendingSubtitle.text,
            candidate.text
        )


    let pendingPosition =
        positionSimilarity(
            pendingSubtitle,
            candidate
        )


    if pendingSimilarity
        >= Config.pendingTextThreshold
        &&
        pendingPosition
            >= 0.35
    {

        pendingCount +=
            1

    } else {

        self.pendingSubtitle =
            candidate

        pendingCount =
            1

        pendingFirstPTS =
            candidate.pts

        return
    }


    guard pendingCount
        >= Config.changedConfirmations
    else {
        return
    }


    let previousSubtitle =
        currentSubtitle


    let changePTS =
        pendingFirstPTS
        ?? candidate.pts


    let previousEndPTS =
        changePTS
        - Config.subtitleEndPadding


    closeCurrentSubtitle(
        at:
            previousEndPTS
    )


    print("")
    print(
        "SUBTITLE_CHANGED"
    )


    print(
        "  pts="
        + format(
            changePTS
        )
    )


    print(
        "  previous="
        + previousSubtitle.text
    )


    print(
        "  current="
        + candidate.text
    )


    print("")


    startNewSubtitle(
        candidate,
        firstPTS:
            changePTS
    )


    self.pendingSubtitle =
        nil

    pendingCount =
        0

    pendingFirstPTS =
        nil
}


private func startNewSubtitle(
    _ candidate:
        SubtitleCandidate,
    firstPTS:
        Double
) {

    subtitleActive =
        true


    currentSubtitle =
        candidate


    currentSubtitleStartPTS =
        firstPTS
        - Config.subtitleStartPadding


    lastSubtitleSeenPTS =
        candidate.pts


    currentSelections =
        []


    currentSegmentID +=
        1


    print(
        "New segment:"
    )


    print(
        "  #"
        + "\(currentSegmentID)"
    )


    print(
        "  audio_start="
        + format(
            currentSubtitleStartPTS
            ?? firstPTS
        )
    )
}


// MARK: - Selection

func selectWord(
    _ word:
        String
) {

    let cleanWord =
        word
            .trimmingCharacters(
                in:
                    .whitespacesAndNewlines
            )


    guard !cleanWord.isEmpty
    else {
        return
    }


    processingQueue.async {

        self.registerSelection(
            cleanWord
        )
    }
}


// Тестовый вызов от глобального X.
func selectCurrentSubtitleForTest() {

    processingQueue.async {

        guard let currentSubtitle =
            self.currentSubtitle,
              self.subtitleActive
        else {

            print("")
            print(
                "SELECTION IGNORED:"
            )

            print(
                "  no active subtitle"
            )

            print("")

            return
        }


        self.registerSelection(
            "[TEST] "
            + currentSubtitle.text
        )
    }
}


private func registerSelection(
    _ word:
        String
) {

    guard let currentSubtitle,
          subtitleActive
    else {

        print("")
        print(
            "SELECTION IGNORED:"
        )

        print(
            "  no active subtitle"
        )

        print("")

        return
    }


    let selectedPTS =
        lastScreenPTS
        ?? currentSubtitle.pts


    if currentSelections.contains(
        where:
        {
            $0.word
                .lowercased()
            ==
            word.lowercased()
        }
    )
    {

        print(
            "Selection already exists:"
        )

        print(
            "  "
            + word
        )

        return
    }


    currentSelections.append(
        WordSelection(
            word:
                word,
            selectedPTS:
                selectedPTS
        )
    )


    print("")
    print(
        "WORD SELECTED"
    )


    print(
        "  word="
        + word
    )


    print(
        "  subtitle="
        + currentSubtitle.text
    )


    print(
        "  segment="
        + "\(currentSegmentID)"
    )


    print(
        "  pts="
        + format(
            selectedPTS
        )
    )


    print(
        "  audio="
        + "waiting for subtitle end"
    )


    print("")
}


// MARK: - Finish subtitle

private func closeCurrentSubtitle(
    at endPTS:
        Double
) {

    guard let currentSubtitle,
          let startPTS =
            currentSubtitleStartPTS
    else {
        return
    }


    let finalEndPTS =
        max(
            startPTS + 0.05,
            endPTS
        )


    let segment =
        SubtitleSegment(
            id:
                currentSegmentID,
            text:
                currentSubtitle.text,
            startPTS:
                startPTS,
            endPTS:
                finalEndPTS,
            selections:
                currentSelections
        )


    completedSegments.append(
        segment
    )


    print(
        "Audio segment registered:"
    )


    print(
        "  #"
        + "\(segment.id)"
    )


    print(
        "  duration="
        + format(
            segment.duration
        )
        + " s"
    )


    print(
        "  selected="
        + (
            segment.selections.isEmpty
            ? "no"
            : "yes"
        )
    )


    if !segment.selections.isEmpty {

        audioRecorder?.exportSegment(
            segment
        )
    }


    currentSubtitleStartPTS =
        nil


    currentSelections =
        []
}


// MARK: - OCR revision

private func isLikelyOCRRevision(
    _ oldText:
        String,
    _ newText:
        String,
    _ position:
        Double
) -> Bool {

    guard position
        >= Config.ocrRevisionPosition
    else {
        return false
    }


    let similarity =
        textSimilarity(
            oldText,
            newText
        )


    if similarity
        >= Config.ocrRevisionSimilarity
    {
        return true
    }


    let oldWords =
        wordTokens(
            oldText
        )


    let newWords =
        wordTokens(
            newText
        )


    let common =
        longestCommonWordSequence(
            oldWords,
            newWords
        )


    return common
        >= Config.ocrRevisionMinimumCommonWords
}


private func wordTokens(
    _ text:
        String
) -> [String] {

    return text
        .lowercased()
        .components(
            separatedBy:
                CharacterSet
                    .alphanumerics
                    .inverted
        )
        .filter {
            !$0.isEmpty
        }
}


private func longestCommonWordSequence(
    _ a:
        [String],
    _ b:
        [String]
) -> Int {

    if a.isEmpty
        || b.isEmpty
    {
        return 0
    }


    var best =
        0


    for i in
        0..<a.count
    {

        for j in
            0..<b.count
        {

            var length =
                0


            while
                i + length < a.count
                &&
                j + length < b.count
                &&
                a[
                    i + length
                ]
                ==
                b[
                    j + length
                ]
            {

                length +=
                    1


                if length >
                    best
                {
                    best =
                        length
                }
            }
        }
    }


    return best
}


// MARK: - Similarity

private func textSimilarity(
    _ a:
        String,
    _ b:
        String
) -> Double {

    if a == b {
        return 1.0
    }


    if a.isEmpty
        || b.isEmpty
    {
        return 0.0
    }


    let aChars =
        Array(a)


    let bChars =
        Array(b)


    var previous =
        Array(
            0...bChars.count
        )


    for i in
        1...aChars.count
    {

        var current =
            Array(
                repeating:
                    0,
                count:
                    bChars.count + 1
            )


        current[0] =
            i


        for j in
            1...bChars.count
        {

            let cost =
                aChars[
                    i - 1
                ]
                ==
                bChars[
                    j - 1
                ]
                ? 0
                : 1


            current[j] =
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + cost
                )
        }


        previous =
            current
    }


    let distance =
        previous[
            bChars.count
        ]


    let maxLength =
        max(
            aChars.count,
            bChars.count
        )


    guard maxLength > 0
    else {
        return 1.0
    }


    return 1.0
        - Double(distance)
        / Double(maxLength)
}


// MARK: - Normalize

private func normalizeText(
    _ text:
        String
) -> String {

    return text
        .lowercased()
        .replacingOccurrences(
            of:
                "\n",
            with:
                " "
        )
        .components(
            separatedBy:
                .whitespacesAndNewlines
        )
        .filter {
            !$0.isEmpty
        }
        .joined(
            separator:
                " "
        )
}


// MARK: - Debug

private func printCandidate(
    _ candidate:
        SubtitleCandidate
) {

    print(
        "  text="
        + candidate.text
    )


    print(
        "  confidence="
        + format(
            Double(
                candidate.confidence
            )
        )
    )


    print(
        "  pts="
        + format(
            candidate.pts
        )
    )


    print(
        "  box="
        + format(candidate.x)
        + ","
        + format(candidate.y)
        + " "
        + format(candidate.width)
        + "x"
        + format(candidate.height)
    )
}


private func printDebugIfNeeded() {

    let now =
        CFAbsoluteTimeGetCurrent()


    guard now - lastDebugTime
        >= Config.debugInterval
    else {
        return
    }


    let averageMS =
        visionCount > 0
        ? (
            totalVisionTime
            / Double(
                visionCount
            )
            * 1000.0
        )
        : 0.0


    print(
        "Stats: "
        + "frames="
        + "\(frameCount), "
        + "vision="
        + "\(visionCount), "
        + "avg="
        + format(
            averageMS
        )
        + " ms, "
        + "active="
        + (
            subtitleActive
            ? "yes"
            : "no"
        )
    )


    if let candidate =
        lastCandidate
    {

        print(
            "  detected=yes"
        )


        print(
            "  text="
            + candidate.text
        )


        print(
            "  confidence="
            + format(
                Double(
                    candidate.confidence
                )
            )
        )


        print(
            "  pts="
            + format(
                candidate.pts
            )
        )

    } else {

        print(
            "  detected=no"
        )
    }


    print(
        "  segment="
        + "\(currentSegmentID)"
    )


    print(
        "  selected_words="
        + "\(currentSelections.count)"
    )


    if let audioRecorder {

        print(
            "  audio_buffers="
            + "\(audioRecorder.audioBufferCount)"
        )

        print(
            "  dropped_audio="
            + "\(audioRecorder.droppedAudioBuffers)"
        )
    }


    frameCount =
        0

    visionCount =
        0

    totalVisionTime =
        0

    lastDebugTime =
        now
}


// MARK: - Manifest

private func writeManifest() {

    guard let audioRecorder
    else {
        return
    }


    let outputURL =
        audioRecorder
            .sessionDirectory
            .appendingPathComponent(
                "segments.json"
            )


    let exported =
        audioRecorder
            .exportResults()


    struct Manifest:
        Codable
    {
        let segments:
            [SubtitleSegment]

        let audioClips:
            [AudioClipResult]
    }


    let manifest =
        Manifest(
            segments:
                completedSegments,
            audioClips:
                exported
        )


    do {

        let encoder =
            JSONEncoder()


        encoder.outputFormatting =
            [
                .prettyPrinted,
                .sortedKeys
            ]


        let data =
            try encoder.encode(
                manifest
            )


        try data.write(
            to:
                outputURL
        )


        print("")
        print(
            "Manifest:"
        )


        print(
            outputURL.path
        )


        print("")

    } catch {

        print(
            "Manifest ERROR: "
            + error.localizedDescription
        )
    }
}


// MARK: - Stop

func stop() async throws {

    guard !stopping else {
        return
    }


    stopping =
        true


    print("")
    print(
        "Stopping..."
    )


    if let stream {

        do {

            try await stream.stopCapture()

        } catch {

            print(
                "Stream stop error: "
                + error.localizedDescription
            )
        }
    }


    // Сначала заканчиваем screen callbacks.
    processingQueue.sync {}


    // Если subtitle ещё активен,
    // закрываем его по последнему реальному screen PTS.
    if subtitleActive {

        let endPTS =
            (
                lastSubtitleSeenPTS
                ?? lastScreenPTS
                ?? 0.0
            )
            + Config.subtitleEndPadding


        closeCurrentSubtitle(
            at:
                endPTS
        )


        subtitleActive =
            false

        currentSubtitle =
            nil
    }


    // Потом дожидаемся audio callbacks.
    audioQueue.sync {}


    guard let audioRecorder
    else {

        print(
            "No audio recorder."
        )

        return
    }


    // Закрываем master.
    audioQueue.sync {

        audioRecorder.finishMaster()
    }


    // Дожидаемся live exports.
    audioRecorder.waitForExports()


    // Если ring buffer не хватил
    // из-за очень длинной паузы,
    // теперь master уже готов.
    audioRecorder.exportDeferredSegments()


    audioRecorder.waitForExports()


    print("")
    print(
        "Subtitle detector stopped."
    )


    print(
        "Master audio:"
    )


    print(
        audioRecorder.masterURL.path
    )


    print(
        "Audio buffers:"
        + " "
        + "\(audioRecorder.audioBufferCount)"
    )


    print(
        "Dropped audio buffers:"
        + " "
        + "\(audioRecorder.droppedAudioBuffers)"
    )


    print(
        "Subtitle segments:"
        + " "
        + "\(completedSegments.count)"
    )


    let exported =
        audioRecorder.exportResults()


    print(
        "Audio clips:"
        + " "
        + "\(exported.count)"
    )


    print("")


    writeManifest()


    print("")
    print(
        "Done."
    )


    print(
        "Session directory:"
    )


    print(
        audioRecorder.sessionDirectory.path
    )


    print("")
}


// MARK: - Stream delegate

func stream(
    _ stream:
        SCStream,
    didStopWithError error:
        Error
) {

    print(
        "Capture stopped:"
    )


    print(
        error.localizedDescription
    )
}


// MARK: - Formatting

private func format(
    _ value:
        Double
) -> String {

    return String(
        format:
            "%.3f",
        value
    )
}
```

}

// MARK: - Global hotkey

var globalHotkeyMonitor:
Any?

func installGlobalHotkey(
detector:
SubtitleDetector
) {

```
if !AXIsProcessTrusted() {

    print("")
    print(
        "WARNING:"
    )

    print(
        "Global X hotkey may not work."
    )

    print(
        "Grant Accessibility/Input Monitoring permission"
    )

    print(
        "to the terminal or the built executable."
    )

    print("")
}


globalHotkeyMonitor =
    NSEvent.addGlobalMonitorForEvents(
        matching:
            .keyDown
    )
    {
        event in

        guard !event.isARepeat
        else {
            return
        }


        guard let characters =
            event.charactersIgnoringModifiers?
                .lowercased()
        else {
            return
        }


        guard characters ==
            Config.selectionKey
        else {
            return
        }


        detector
            .selectCurrentSubtitleForTest()
    }


if globalHotkeyMonitor == nil {

    print(
        "Global hotkey monitor could not be installed."
    )
}
```

}

// MARK: - Main

let detector =
SubtitleDetector()

installGlobalHotkey(
detector:
detector
)

let signalSource =
DispatchSource.makeSignalSource(
signal:
SIGINT,
queue:
DispatchQueue.main
)

signal(
SIGINT,
SIG_IGN
)

signalSource.setEventHandler {

```
Task {

    do {

        try await detector.stop()

        exit(0)

    } catch {

        print(
            "ERROR: "
            + error.localizedDescription
        )

        exit(1)
    }
}
```

}

signalSource.resume()

Task {

```
do {

    try await detector.start()

} catch {

    print(
        "ERROR: "
        + error.localizedDescription
    )

    exit(1)
}
```

}

RunLoop.main.run()
