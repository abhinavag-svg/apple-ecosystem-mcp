import AppKit
import Contacts
import EventKit
import Foundation

enum ServiceState: String {
    case granted = "Granted"
    case denied = "Needs Access"
    case unknown = "Not Checked"
}

struct ServiceStatus {
    let name: String
    let state: ServiceState
}

@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let eventStore = EKEventStore()
    private let contactStore = CNContactStore()
    private var statuses: [ServiceStatus] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem.button?.title = "Apple Ecosystem"
        refreshStatuses()
    }

    private func rebuildMenu() {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Apple Ecosystem MCP", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())

        for status in statuses {
            let item = NSMenuItem(title: "\(status.name): \(status.state.rawValue)", action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        }

        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Request Calendar Access", action: #selector(requestCalendarAccess), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Request Contacts Access", action: #selector(requestContactsAccess), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Request Reminders Access", action: #selector(requestRemindersAccess), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Check Mail Automation", action: #selector(checkMailAutomation), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Check Notes Automation", action: #selector(checkNotesAutomation), keyEquivalent: ""))

        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Open Automation Settings", action: #selector(openAutomationSettings), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Full Disk Access Settings", action: #selector(openFullDiskAccessSettings), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Copy Dev Checkout Command", action: #selector(copyDevCheckoutCommand), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Configure Claude Desktop For Dev Checkout", action: #selector(configureClaudeDesktopForDevCheckout), keyEquivalent: ""))

        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Refresh", action: #selector(refreshStatusesAction), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q"))
        statusItem.menu = menu
    }

    @objc private func refreshStatusesAction() {
        refreshStatuses()
    }

    private func refreshStatuses() {
        statuses = [
            ServiceStatus(name: "Mail Automation", state: automationState(applicationName: "Mail")),
            ServiceStatus(name: "Notes Automation", state: automationState(applicationName: "Notes")),
            ServiceStatus(name: "Calendar", state: eventKitState(entityType: .event)),
            ServiceStatus(name: "Contacts", state: contactsState()),
            ServiceStatus(name: "Reminders", state: eventKitState(entityType: .reminder)),
            ServiceStatus(name: "iCloud / Full Disk", state: fullDiskAccessState()),
        ]
        rebuildMenu()
    }

    private func eventKitState(entityType: EKEntityType) -> ServiceState {
        let status = EKEventStore.authorizationStatus(for: entityType)
        switch status {
        case .authorized, .fullAccess:
            return .granted
        case .denied, .restricted, .writeOnly:
            return .denied
        case .notDetermined:
            return .unknown
        @unknown default:
            return .unknown
        }
    }

    private func contactsState() -> ServiceState {
        switch CNContactStore.authorizationStatus(for: .contacts) {
        case .authorized:
            return .granted
        case .denied, .restricted, .limited:
            return .denied
        case .notDetermined:
            return .unknown
        @unknown default:
            return .unknown
        }
    }

    private func fullDiskAccessState() -> ServiceState {
        let path = ("~/Library/Mobile Documents/com~apple~CloudDocs" as NSString).expandingTildeInPath
        do {
            _ = try FileManager.default.contentsOfDirectory(atPath: path)
            return .granted
        } catch CocoaError.fileReadNoPermission {
            return .denied
        } catch {
            return .unknown
        }
    }

    private func automationState(applicationName: String) -> ServiceState {
        let source = """
        tell application "\(applicationName)"
          return name
        end tell
        """
        var errorInfo: NSDictionary?
        let result = NSAppleScript(source: source)?.executeAndReturnError(&errorInfo)
        if result?.stringValue == applicationName {
            return .granted
        }
        let errorNumber = errorInfo?[NSAppleScript.errorNumber] as? Int
        if errorNumber == -1743 {
            return .denied
        }
        return .unknown
    }

    @objc private func requestCalendarAccess() {
        requestEventKitAccess(entityType: .event)
    }

    @objc private func requestRemindersAccess() {
        requestEventKitAccess(entityType: .reminder)
    }

    private func requestEventKitAccess(entityType: EKEntityType) {
        if #available(macOS 14.0, *) {
            if entityType == .event {
                eventStore.requestFullAccessToEvents { _, _ in
                    DispatchQueue.main.async { self.refreshStatuses() }
                }
            } else {
                eventStore.requestFullAccessToReminders { _, _ in
                    DispatchQueue.main.async { self.refreshStatuses() }
                }
            }
        } else {
            eventStore.requestAccess(to: entityType) { _, _ in
                DispatchQueue.main.async { self.refreshStatuses() }
            }
        }
    }

    @objc private func requestContactsAccess() {
        contactStore.requestAccess(for: .contacts) { _, _ in
            DispatchQueue.main.async { self.refreshStatuses() }
        }
    }

    @objc private func checkMailAutomation() {
        _ = automationState(applicationName: "Mail")
        refreshStatuses()
    }

    @objc private func checkNotesAutomation() {
        _ = automationState(applicationName: "Notes")
        refreshStatuses()
    }

    @objc private func openAutomationSettings() {
        openSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
    }

    @objc private func openFullDiskAccessSettings() {
        openSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
    }

    private func openSettings(_ value: String) {
        guard let url = URL(string: value) else { return }
        NSWorkspace.shared.open(url)
    }

    @objc private func copyDevCheckoutCommand() {
        let environment = ProcessInfo.processInfo.environment
        guard let projectDir = environment["APPLE_ECOSYSTEM_MCP_PROJECT_DIR"], !projectDir.isEmpty else {
            showAlert(
                title: "Project Directory Missing",
                message: "Set APPLE_ECOSYSTEM_MCP_PROJECT_DIR before copying a dev-checkout command."
            )
            return
        }
        let command = "claude mcp add --scope user apple-ecosystem -- uv run --project \(shellQuote(projectDir)) apple-ecosystem-mcp"
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(command, forType: .string)
    }

    private func shellQuote(_ value: String) -> String {
        return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    @objc private func configureClaudeDesktopForDevCheckout() {
        let environment = ProcessInfo.processInfo.environment
        guard let projectDir = environment["APPLE_ECOSYSTEM_MCP_PROJECT_DIR"], !projectDir.isEmpty else {
            showAlert(
                title: "Project Directory Missing",
                message: "Set APPLE_ECOSYSTEM_MCP_PROJECT_DIR before using dev-checkout configuration."
            )
            return
        }

        let configPath = ("~/Library/Application Support/Claude/claude_desktop_config.json" as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: configPath)
        let manager = FileManager.default
        try? manager.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)

        var root: [String: Any] = [:]
        if let data = try? Data(contentsOf: url),
           let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            root = parsed
        }

        var servers = root["mcpServers"] as? [String: Any] ?? [:]
        servers["apple-ecosystem"] = [
            "command": "uv",
            "args": ["run", "--project", projectDir, "apple-ecosystem-mcp"],
        ]
        root["mcpServers"] = servers

        do {
            let data = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: url, options: [.atomic])
            showAlert(title: "Claude Desktop Updated", message: "Restart Claude Desktop to load the dev checkout.")
        } catch {
            showAlert(title: "Could Not Update Claude Desktop", message: error.localizedDescription)
        }
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    @objc private func quit() {
        NSApplication.shared.terminate(nil)
    }
}
