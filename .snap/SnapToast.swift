import AppKit
import Foundation
import Darwin

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let mouse = NSEvent.mouseLocation

let selectedScreen =
    NSScreen.screens.first(where: { $0.frame.contains(mouse) })
    ?? NSScreen.main
    ?? NSScreen.screens.first

guard let screen = selectedScreen else {
    exit(1)
}

let icon = NSImageView()
let symbolConfig = NSImage.SymbolConfiguration(pointSize: 19, weight: .semibold)
    .applying(NSImage.SymbolConfiguration(paletteColors: [
        .white,
        NSColor(calibratedRed: 0.20, green: 0.78, blue: 0.40, alpha: 1.0)
    ]))

if let image = NSImage(
    systemSymbolName: "checkmark.circle.fill",
    accessibilityDescription: nil
) {
    icon.image = image.withSymbolConfiguration(symbolConfig) ?? image
}
icon.translatesAutoresizingMaskIntoConstraints = false

let label = NSTextField(labelWithString: "Card added")
label.font = NSFont.systemFont(ofSize: 14, weight: .semibold)
label.textColor = NSColor.white.withAlphaComponent(0.95)

let stack = NSStackView(views: [icon, label])
stack.orientation = .horizontal
stack.alignment = .centerY
stack.spacing = 9
stack.translatesAutoresizingMaskIntoConstraints = false

let height: CGFloat = 46
let horizontalPadding: CGFloat = 20
let width = ceil(stack.fittingSize.width) + horizontalPadding * 2
let radius = height / 2

let visible = screen.visibleFrame
let x = visible.midX - width / 2
let targetY = visible.minY + visible.height * 0.17
let startY = targetY - 10

let panel = NSPanel(
    contentRect: NSRect(x: x, y: startY, width: width, height: height),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)

panel.level = .screenSaver
panel.collectionBehavior = [
    .canJoinAllSpaces,
    .fullScreenAuxiliary,
    .ignoresCycle
]
panel.isFloatingPanel = true
panel.becomesKeyOnlyIfNeeded = true
panel.hidesOnDeactivate = false
panel.ignoresMouseEvents = true
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
panel.appearance = NSAppearance(named: .darkAqua)

let mask = NSImage(
    size: NSSize(width: height, height: height),
    flipped: false
) { rect in
    NSColor.black.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
    return true
}
mask.capInsets = NSEdgeInsets(top: radius, left: radius, bottom: radius, right: radius)
mask.resizingMode = .stretch

let content = NSVisualEffectView(
    frame: NSRect(x: 0, y: 0, width: width, height: height)
)
content.material = .hudWindow
content.blendingMode = .behindWindow
content.state = .active
content.appearance = NSAppearance(named: .darkAqua)
content.maskImage = mask

content.addSubview(stack)

NSLayoutConstraint.activate([
    icon.widthAnchor.constraint(equalToConstant: 20),
    icon.heightAnchor.constraint(equalToConstant: 20),
    stack.centerXAnchor.constraint(equalTo: content.centerXAnchor),
    stack.centerYAnchor.constraint(equalTo: content.centerYAnchor)
])

panel.contentView = content
panel.alphaValue = 0
panel.orderFrontRegardless()

NSAnimationContext.runAnimationGroup { context in
    context.duration = 0.22
    context.timingFunction = CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.3, 1.0)
    panel.animator().alphaValue = 1
    panel.animator().setFrame(
        NSRect(x: x, y: targetY, width: width, height: height),
        display: true
    )
}

DispatchQueue.main.asyncAfter(deadline: .now() + 1.3) {
    NSAnimationContext.runAnimationGroup({ context in
        context.duration = 0.2
        context.timingFunction = CAMediaTimingFunction(name: .easeIn)
        panel.animator().alphaValue = 0
        panel.animator().setFrame(
            NSRect(x: x, y: targetY + 6, width: width, height: height),
            display: true
        )
    }, completionHandler: {
        app.terminate(nil)
    })
}

app.run()
