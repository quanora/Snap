import Foundation
import Darwin
import CoreGraphics
import CoreMedia
import CoreVideo
import ScreenCaptureKit
import Vision


enum Config {

    static let fps = 5

    static let captureWidth = 768
    static let captureHeight = 497

    // Почти весь экран по Y.
    // Это специально, чтобы не зависеть от того,
    // находятся субтитры в видео, в black bar
    // или чуть выше/ниже привычного места.
    static let roiX = 0.02
    static let roiY = 0.02
    static let roiWidth = 0.96
    static let roiHeight = 0.90

    // Vision.
    static let minimumConfidence: Float = 0.20
    static let minimumTextHeight: Float = 0.006

    // Отбрасываем совсем микроскопический текст.
    static let minimumWidth = 0.012

    // Не берём гигантские текстовые блоки.
    static let maximumHeight = 0.16

    // Минимум символов.
    static let minimumCharacters = 2

    // При отсутствии OCR несколько кадров подряд
    // не считаем субтитр сразу исчезнувшим.
    static let disappearedFrames = 6

    // Сколько подтверждений нужно для появления.
    static let appearedConfirmations = 2

    // Сколько подтверждений нужно для смены.
    static let changedConfirmations = 2

    // Если OCR немного изменил написание той же строки,
    // считаем её той же самой репликой.
    static let sameTextThreshold = 0.85

    // Насколько похожими должны быть два
    // последовательных кандидата новой реплики.
    static let pendingTextThreshold = 0.72

    // Насколько близко должен находиться текст
    // к предыдущему тексту.
    static let samePositionThreshold = 0.55

    static let debugInterval = 2.0

    static let successSound =
        "/System/Library/Sounds/Funk.aiff"

    static let changeSound =
        "/System/Library/Sounds/Pop.aiff"

    static let disappearSound =
        "/System/Library/Sounds/Sosumi.aiff"
}


struct RuntimeError:
    Error,
    LocalizedError
{

    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? {
        return message
    }
}


struct SubtitleCandidate {

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
}


final class SubtitleDetector:
    NSObject,
    SCStreamOutput,
    SCStreamDelegate
{

    private var stream: SCStream?

    private let processingQueue =
        DispatchQueue(
            label:
                "snap.subtitle.detector",
            qos:
                .utility
        )

    private var subtitleActive =
        false

    private var currentSubtitle:
        SubtitleCandidate?

    private var pendingSubtitle:
        SubtitleCandidate?

    private var pendingCount =
        0

    private var missingFrames =
        0

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


    func start() async throws {

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
                where: {
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
        _ display: SCDisplay
    ) async throws {

        print("")
        print(
            "Snap Subtitle Watch"
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

        print("")

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
            3

        configuration.showsCursor =
            false

        configuration.capturesAudio =
            false

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

        stream =
            newStream

        try await newStream.startCapture()

        print(
            "Capture started."
        )

        print(
            "Press Ctrl+C to stop."
        )

        print("")
    }


    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer:
            CMSampleBuffer,
        of type:
            SCStreamOutputType
    ) {

        guard type == .screen else {
            return
        }

        guard sampleBuffer.isValid else {
            return
        }

        guard let pixelBuffer =
            CMSampleBufferGetImageBuffer(
                sampleBuffer
            )
        else {
            return
        }

        let start =
            CFAbsoluteTimeGetCurrent()

        let pts =
            CMTimeGetSeconds(
                CMSampleBufferGetPresentationTimeStamp(
                    sampleBuffer
                )
            )

        let candidate =
            detectSubtitle(
                pixelBuffer,
                pts:
                    pts
            )

        lastCandidate =
            candidate

        processCandidate(
            candidate
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


    private func detectSubtitle(
        _ pixelBuffer:
            CVPixelBuffer,
        pts:
            Double
    ) -> SubtitleCandidate? {

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
                    request
                ]
            )

        } catch {

            return nil
        }

        guard let observations =
            request.results
        else {
            return nil
        }

        var candidates:
            [SubtitleCandidate] = []

        for observation in observations {

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

            // Полностью верхнюю/нижнюю служебную область
            // не рассматриваем.
            guard centerY >= 0.03,
                  centerY <= 0.90
            else {
                continue
            }

            let candidate =
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

            candidates.append(
                candidate
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
    ) -> SubtitleCandidate? {

        var best:
            SubtitleCandidate?

        var bestScore =
            -Double.infinity

        for candidate in candidates {

            var score =
                0.0

            let widthScore =
                min(
                    1.0,
                    candidate.width
                    / 0.60
                )

            let characterScore =
                min(
                    1.0,
                    Double(
                        candidate.text.count
                    )
                    / 40.0
                )

            // Для первой реплики слегка предпочитаем
            // нижнюю часть экрана, но не требуем её.
            let subtitlePositionScore =
                positionScore(
                    candidate
                )

            score +=
                widthScore
                * 2.0

            score +=
                characterScore
                * 1.0

            score +=
                subtitlePositionScore
                * 1.5

            if let currentSubtitle {

                let textSimilarity =
                    textSimilarity(
                        currentSubtitle.text,
                        candidate.text
                    )

                let positionSimilarity =
                    positionSimilarity(
                        currentSubtitle,
                        candidate
                    )

                score +=
                    textSimilarity
                    * 4.0

                score +=
                    positionSimilarity
                    * 3.0
            }

            if let best {

                let similarityToBest =
                    textSimilarity(
                        best.text,
                        candidate.text
                    )

                if similarityToBest >=
                    0.90
                {
                    score += 1.5
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

        // Субтитры чаще находятся в нижней части,
        // но разрешаем им находиться практически где угодно.
        let distance =
            abs(
                centerY - 0.22
            )

        let yScore =
            max(
                0.0,
                1.0
                - distance / 0.65
            )

        let centerDistance =
            abs(
                candidate.centerX - 0.5
            )

        let xScore =
            max(
                0.0,
                1.0
                - centerDistance / 0.5
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
                a.centerX
                - b.centerX
            )

        let centerDistanceY =
            abs(
                a.centerY
                - b.centerY
            )

        let widthDifference =
            abs(
                a.width
                - b.width
            )

        let heightDifference =
            abs(
                a.height
                - b.height
            )

        let xScore =
            max(
                0.0,
                1.0
                - centerDistanceX / 0.45
            )

        let yScore =
            max(
                0.0,
                1.0
                - centerDistanceY / 0.15
            )

        let widthScore =
            max(
                0.0,
                1.0
                - widthDifference / 0.50
            )

        let heightScore =
            max(
                0.0,
                1.0
                - heightDifference / 0.12
            )

        return (
            xScore * 0.30
            + yScore * 0.40
            + widthScore * 0.20
            + heightScore * 0.10
        )
    }


    private func processCandidate(
        _ candidate:
            SubtitleCandidate?
    ) {

        guard let candidate else {

            missingFrames +=
                1

            pendingSubtitle =
                nil

            pendingCount =
                0

            if subtitleActive
                && missingFrames
                >= Config.disappearedFrames
            {

                subtitleActive =
                    false

                currentSubtitle =
                    nil

                pendingSubtitle =
                    nil

                print("")
                print(
                    "SUBTITLE_DISAPPEARED"
                )

                print(
                    "  pts="
                    + formatPTS()
                )

                print("")

                playSound(
                    Config.disappearSound
                )
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
        }

        if pendingCount
            >= Config.appearedConfirmations
        {

            subtitleActive =
                true

            currentSubtitle =
                candidate

            self.pendingSubtitle =
                nil

            pendingCount =
                0

            print("")
            print(
                "SUBTITLE_APPEARED"
            )

            printCandidate(
                candidate
            )

            print("")

            playSound(
                Config.successSound
            )
        }
    }


    private func processActiveSubtitle(
        _ candidate:
            SubtitleCandidate
    ) {

        guard let currentSubtitle
        else {

            self.currentSubtitle =
                candidate

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

        // Тот же текст, возможно немного
        // по-другому распознанный.
        if similarity
            >= Config.sameTextThreshold
            || (
                similarity >= 0.72
                && position
                    >= Config.samePositionThreshold
            )
        {

            self.currentSubtitle =
                candidate

            pendingSubtitle =
                nil

            pendingCount =
                0

            return
        }

        // Мы получили возможную новую реплику.
        guard let pendingSubtitle
        else {

            self.pendingSubtitle =
                candidate

            pendingCount =
                1

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
            && pendingPosition
            >= 0.35
        {

            pendingCount +=
                1

        } else {

            self.pendingSubtitle =
                candidate

            pendingCount =
                1

            return
        }

        if pendingCount
            >= Config.changedConfirmations
        {

            self.currentSubtitle =
                candidate

            self.pendingSubtitle =
                nil

            pendingCount =
                0

            print("")
            print(
                "SUBTITLE_CHANGED"
            )

            print(
                "  pts="
                + format(
                    candidate.pts
                )
            )

            print(
                "  previous="
                + currentSubtitle.text
            )

            print(
                "  current="
                + candidate.text
            )

            print(
                "  similarity="
                + format(
                    similarity
                )
            )

            print(
                "  position="
                + format(
                    position
                )
            )

            print("")

            playSound(
                Config.changeSound
            )
        }
    }


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

        for i in 1...aChars.count {

            var current =
                Array(
                    repeating:
                        0,
                    count:
                        bChars.count + 1
                )

            current[0] =
                i

            for j in 1...bChars.count {

                let cost =
                    aChars[i - 1]
                    ==
                    bChars[j - 1]
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

        guard maxLength > 0 else {
            return 1.0
        }

        return 1.0
            - Double(distance)
            / Double(maxLength)
    }


    private func normalizeText(
        _ text:
            String
    ) -> String {

        let lower =
            text
                .lowercased()
                .replacingOccurrences(
                    of:
                        "\n",
                    with:
                        " "
                )

        return lower
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
            + format(
                candidate.x
            )
            + ","
            + format(
                candidate.y
            )
            + " "
            + format(
                candidate.width
            )
            + "x"
            + format(
                candidate.height
            )
        )
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


    private func formatPTS() -> String {

        if let lastCandidate {

            return format(
                lastCandidate.pts
            )
        }

        return "unknown"
    }


    private func playSound(
        _ path:
            String
    ) {

        guard FileManager.default.fileExists(
            atPath:
                path
        )
        else {
            return
        }

        Process.launchedProcess(
            launchPath:
                "/usr/bin/afplay",
            arguments:
                [path]
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

        let averageMs =
            visionCount > 0
            ? (
                totalVisionTime
                / Double(visionCount)
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
                averageMs
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

        frameCount =
            0

        visionCount =
            0

        totalVisionTime =
            0

        lastDebugTime =
            now
    }


    func stream(
        _ stream: SCStream,
        didStopWithError error:
            Error
    ) {

        print(
            "Capture stopped: "
            + error.localizedDescription
        )
    }
}


let detector =
    SubtitleDetector()

Task {

    do {

        try await detector.start()

    } catch {

        print(
            "ERROR: "
            + String(
                describing:
                    error
            )
        )

        exit(1)
    }
}

RunLoop.main.run()