import Contacts
import EventKit
import Foundation

typealias JSON = [String: Any]

struct HelperError: Error {
    let code: String
    let message: String
    let recoverable: Bool
}

func success(_ result: Any) -> JSON {
    ["ok": true, "result": result]
}

func failure(_ code: String, _ message: String, recoverable: Bool = true) -> JSON {
    [
        "ok": false,
        "error": [
            "code": code,
            "message": message,
            "recoverable": recoverable,
        ],
    ]
}

func writeJSON(_ object: Any) {
    let data = try! JSONSerialization.data(withJSONObject: object, options: [])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

func readPayload() throws -> JSON {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    if data.isEmpty { return [:] }
    let object = try JSONSerialization.jsonObject(with: data)
    return object as? JSON ?? [:]
}

func string(_ payload: JSON, _ key: String) -> String? {
    guard let value = payload[key] else { return nil }
    if value is NSNull { return nil }
    let text = String(describing: value)
    return text.isEmpty ? nil : text
}

func bool(_ payload: JSON, _ key: String, default defaultValue: Bool = false) -> Bool {
    if let value = payload[key] as? Bool { return value }
    if let value = payload[key] as? String { return ["1", "true", "yes"].contains(value.lowercased()) }
    return defaultValue
}

func int(_ payload: JSON, _ key: String, default defaultValue: Int) -> Int {
    if let value = payload[key] as? Int { return value }
    if let value = payload[key] as? Double { return Int(value) }
    if let value = payload[key] as? String, let parsed = Int(value) { return parsed }
    return defaultValue
}

func stringArray(_ payload: JSON, _ key: String) -> [String] {
    (payload[key] as? [Any] ?? []).compactMap { value in
        if value is NSNull { return nil }
        let text = String(describing: value)
        return text.isEmpty ? nil : text
    }
}

let isoFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
}()

let isoFormatterNoFraction: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter
}()

let localFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone.current
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    return formatter
}()

func parseDate(_ value: String?) throws -> Date {
    guard let value else { throw HelperError(code: "invalid_input", message: "Missing date", recoverable: false) }
    if let date = isoFormatter.date(from: value) { return date }
    if let date = isoFormatterNoFraction.date(from: value) { return date }
    if let date = localFormatter.date(from: value) { return date }
    throw HelperError(code: "invalid_input", message: "Invalid ISO 8601 date", recoverable: false)
}

func emitDate(_ date: Date?) -> Any {
    guard let date else { return NSNull() }
    return localFormatter.string(from: date)
}

func requireEventAccess(_ store: EKEventStore, entityType: EKEntityType) throws {
    let status = EKEventStore.authorizationStatus(for: entityType)
    if #available(macOS 14.0, *) {
        if status == .fullAccess { return }
    } else if status == .authorized {
        return
    }
    if status == .denied || status == .restricted {
        throw HelperError(code: "permission_denied", message: "Native access is denied in macOS privacy settings.", recoverable: true)
    }

    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    var requestError: Error?

    if entityType == .event {
        if #available(macOS 14.0, *) {
            store.requestFullAccessToEvents { ok, error in
                granted = ok
                requestError = error
                semaphore.signal()
            }
        } else {
            store.requestAccess(to: .event) { ok, error in
                granted = ok
                requestError = error
                semaphore.signal()
            }
        }
    } else {
        if #available(macOS 14.0, *) {
            store.requestFullAccessToReminders { ok, error in
                granted = ok
                requestError = error
                semaphore.signal()
            }
        } else {
            store.requestAccess(to: .reminder) { ok, error in
                granted = ok
                requestError = error
                semaphore.signal()
            }
        }
    }

    _ = semaphore.wait(timeout: .now() + 30)
    if let requestError {
        let message = requestError.localizedDescription
        if message.localizedCaseInsensitiveContains("access denied") {
            throw HelperError(code: "permission_denied", message: "Native access is denied in macOS privacy settings.", recoverable: true)
        }
        throw HelperError(code: "native_backend_error", message: message, recoverable: true)
    }
    if !granted {
        throw HelperError(code: "permission_not_determined", message: "Native access has not been granted yet.", recoverable: true)
    }
}

func requireContactsAccess(_ store: CNContactStore) throws {
    let status = CNContactStore.authorizationStatus(for: .contacts)
    if status == .authorized { return }
    if status == .denied || status == .restricted {
        throw HelperError(code: "permission_denied", message: "Contacts access is denied in macOS privacy settings.", recoverable: true)
    }

    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    var requestError: Error?
    store.requestAccess(for: .contacts) { ok, error in
        granted = ok
        requestError = error
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 30)
    if let requestError {
        let message = requestError.localizedDescription
        if message.localizedCaseInsensitiveContains("access denied") {
            throw HelperError(code: "permission_denied", message: "Contacts access is denied in macOS privacy settings.", recoverable: true)
        }
        throw HelperError(code: "native_backend_error", message: message, recoverable: true)
    }
    if !granted {
        throw HelperError(code: "permission_not_determined", message: "Contacts access has not been granted yet.", recoverable: true)
    }
}

func calendarRow(_ calendar: EKCalendar, defaultCandidate: Bool = false) -> JSON {
    [
        "id": calendar.calendarIdentifier,
        "uid": calendar.calendarIdentifier,
        "name": calendar.title,
        "kind": "calendar",
        "account_name": calendar.source.title,
        "path": NSNull(),
        "writable": calendar.allowsContentModifications,
        "default_candidate": defaultCandidate,
    ]
}

func eventRow(_ event: EKEvent) -> JSON {
    let attendees = (event.attendees ?? []).compactMap { participant -> String? in
        let text = participant.url.absoluteString
        if text.hasPrefix("mailto:") {
            return String(text.dropFirst("mailto:".count))
        }
        return text.isEmpty ? nil : text
    }
    let uid = event.eventIdentifier ?? event.calendarItemIdentifier
    return [
        "uid": uid,
        "title": event.title ?? "",
        "start": emitDate(event.startDate),
        "end": emitDate(event.endDate),
        "location": event.location ?? NSNull(),
        "notes": event.notes ?? NSNull(),
        "url": event.url?.absoluteString ?? NSNull(),
        "all_day": event.isAllDay,
        "calendar_uid": event.calendar.calendarIdentifier,
        "calendar_name": event.calendar.title,
        "attendees": attendees,
        "invitees": attendees,
    ]
}

func findCalendar(_ store: EKEventStore, _ identifier: String?) -> EKCalendar? {
    guard let identifier, !identifier.isEmpty else {
        return store.defaultCalendarForNewEvents ?? store.calendars(for: .event).first(where: { $0.allowsContentModifications })
    }
    return store.calendars(for: .event).first { $0.calendarIdentifier == identifier || $0.title == identifier }
}

func handleCalendar(_ operation: String, _ payload: JSON) throws -> Any {
    if operation == "health" { return ["status": "ok"] }
    let store = EKEventStore()
    try requireEventAccess(store, entityType: .event)

    switch operation {
    case "list-calendars":
        var marked = false
        return store.calendars(for: .event).map { calendar in
            let isDefault = !marked && calendar.allowsContentModifications
            if isDefault { marked = true }
            return calendarRow(calendar, defaultCandidate: isDefault)
        }
    case "list-events":
        let start = try parseDate(string(payload, "start"))
        let end = try parseDate(string(payload, "end"))
        let calendarID = string(payload, "calendar_uid")
        let calendars = calendarID.flatMap { findCalendar(store, $0).map { [$0] } }
        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
        let limit = max(1, min(int(payload, "limit", default: 50), 200))
        return Array(store.events(matching: predicate).prefix(limit)).map(eventRow)
    case "get-event":
        guard let eventID = string(payload, "event_id"), let event = store.event(withIdentifier: eventID) else {
            throw HelperError(code: "not_found", message: "Event not found", recoverable: false)
        }
        return eventRow(event)
    case "create-event":
        guard let calendar = findCalendar(store, string(payload, "calendar_uid")) else {
            throw HelperError(code: "not_found", message: "Calendar not found", recoverable: false)
        }
        if !calendar.allowsContentModifications {
            throw HelperError(code: "not_writable", message: "Calendar is not writable", recoverable: false)
        }
        let event = EKEvent(eventStore: store)
        event.calendar = calendar
        event.title = string(payload, "title") ?? ""
        event.startDate = try parseDate(string(payload, "start"))
        event.endDate = try parseDate(string(payload, "end"))
        event.location = string(payload, "location")
        event.notes = string(payload, "notes")
        if let urlText = string(payload, "url") { event.url = URL(string: urlText) }
        event.isAllDay = bool(payload, "all_day")
        try store.save(event, span: .thisEvent, commit: true)
        return ["uid": event.eventIdentifier ?? event.calendarItemIdentifier]
    case "update-event":
        guard let eventID = string(payload, "event_id"), let event = store.event(withIdentifier: eventID) else {
            throw HelperError(code: "not_found", message: "Event not found", recoverable: false)
        }
        if !event.calendar.allowsContentModifications {
            throw HelperError(code: "not_writable", message: "Calendar is not writable", recoverable: false)
        }
        if let title = string(payload, "title") { event.title = title }
        if let start = string(payload, "start") { event.startDate = try parseDate(start) }
        if let end = string(payload, "end") { event.endDate = try parseDate(end) }
        if bool(payload, "clear_location") { event.location = nil } else if let location = string(payload, "location") { event.location = location }
        if bool(payload, "clear_notes") { event.notes = nil } else if let notes = string(payload, "notes") { event.notes = notes }
        if bool(payload, "clear_url") { event.url = nil } else if let urlText = string(payload, "url") { event.url = URL(string: urlText) }
        if payload.keys.contains("all_day") { event.isAllDay = bool(payload, "all_day") }
        try store.save(event, span: .thisEvent, commit: true)
        return ["uid": event.eventIdentifier ?? event.calendarItemIdentifier]
    case "delete-event":
        guard let eventID = string(payload, "event_id"), let event = store.event(withIdentifier: eventID) else {
            throw HelperError(code: "not_found", message: "Event not found", recoverable: false)
        }
        if !event.calendar.allowsContentModifications {
            throw HelperError(code: "not_writable", message: "Calendar is not writable", recoverable: false)
        }
        try store.remove(event, span: .thisEvent, commit: true)
        return ["uid": eventID]
    case "search":
        let query = (string(payload, "query") ?? "").lowercased()
        let start = try parseDate(string(payload, "start"))
        let end = try parseDate(string(payload, "end"))
        let calendarID = string(payload, "calendar_uid")
        let calendars = calendarID.flatMap { findCalendar(store, $0).map { [$0] } }
        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
        let limit = max(1, min(int(payload, "limit", default: 50), 200))
        return store.events(matching: predicate).filter { event in
            if query.isEmpty { return true }
            if (event.title ?? "").lowercased().contains(query) { return true }
            if (event.location ?? "").lowercased().contains(query) { return true }
            if (event.notes ?? "").lowercased().contains(query) { return true }
            return false
        }.prefix(limit).map(eventRow)
    default:
        throw HelperError(code: "invalid_operation", message: "Unsupported calendar operation", recoverable: false)
    }
}

func reminderListRow(_ calendar: EKCalendar, defaultCandidate: Bool = false) -> JSON {
    [
        "id": calendar.calendarIdentifier,
        "name": calendar.title,
        "kind": "reminder_list",
        "account_name": calendar.source.title,
        "path": NSNull(),
        "writable": calendar.allowsContentModifications,
        "default_candidate": defaultCandidate,
    ]
}

func reminderRow(_ reminder: EKReminder) -> JSON {
    let due = reminder.dueDateComponents.flatMap { Calendar.current.date(from: $0) }
    return [
        "id": reminder.calendarItemIdentifier,
        "title": reminder.title ?? "",
        "notes": reminder.notes ?? NSNull(),
        "due": emitDate(due),
        "priority": reminder.priority,
        "list_name": reminder.calendar.title,
        "list_id": reminder.calendar.calendarIdentifier,
        "recurrence": NSNull(),
        "tags": [],
        "completed": reminder.isCompleted,
    ]
}

func findReminderCalendar(_ store: EKEventStore, id: String?, name: String?) -> EKCalendar? {
    let calendars = store.calendars(for: .reminder)
    if let id, !id.isEmpty, let match = calendars.first(where: { $0.calendarIdentifier == id }) { return match }
    if let name, !name.isEmpty, let match = calendars.first(where: { $0.title == name }) { return match }
    return store.defaultCalendarForNewReminders() ?? calendars.first(where: { $0.allowsContentModifications })
}

func writableReminderSource(_ store: EKEventStore) -> EKSource? {
    if let source = store.defaultCalendarForNewReminders()?.source { return source }
    return store.sources.first { source in
        !source.calendars(for: .reminder).isEmpty || source.sourceType == .calDAV || source.sourceType == .local
    }
}

func fetchReminders(_ store: EKEventStore, predicate: NSPredicate) throws -> [EKReminder] {
    let semaphore = DispatchSemaphore(value: 0)
    var output: [EKReminder] = []
    store.fetchReminders(matching: predicate) { reminders in
        output = reminders ?? []
        semaphore.signal()
    }
    if semaphore.wait(timeout: .now() + 20) == .timedOut {
        throw HelperError(code: "helper_timeout", message: "Reminder fetch timed out", recoverable: true)
    }
    return output
}

func handleReminders(_ operation: String, _ payload: JSON) throws -> Any {
    if operation == "health" { return ["status": "ok"] }
    let store = EKEventStore()
    try requireEventAccess(store, entityType: .reminder)

    switch operation {
    case "list-lists":
        var marked = false
        return store.calendars(for: .reminder).map { calendar in
            let isDefault = !marked
            if isDefault { marked = true }
            return reminderListRow(calendar, defaultCandidate: isDefault)
        }
    case "create-list":
        guard let name = string(payload, "name") else {
            throw HelperError(code: "invalid_input", message: "Missing reminder list name", recoverable: false)
        }
        guard let source = writableReminderSource(store) else {
            throw HelperError(code: "not_found", message: "No writable reminder source found", recoverable: false)
        }
        let calendar = EKCalendar(for: .reminder, eventStore: store)
        calendar.title = name
        calendar.source = source
        try store.saveCalendar(calendar, commit: true)
        return reminderListRow(calendar)
    case "rename-list":
        guard let calendar = findReminderCalendar(store, id: string(payload, "reminders_list_id"), name: string(payload, "old_name")) else {
            throw HelperError(code: "not_found", message: "Reminder list not found", recoverable: false)
        }
        guard let newName = string(payload, "new_name") else {
            throw HelperError(code: "invalid_input", message: "Missing new reminder list name", recoverable: false)
        }
        calendar.title = newName
        try store.saveCalendar(calendar, commit: true)
        return reminderListRow(calendar)
    case "delete-list":
        guard let calendar = findReminderCalendar(store, id: string(payload, "reminders_list_id"), name: string(payload, "name")) else {
            throw HelperError(code: "not_found", message: "Reminder list not found", recoverable: false)
        }
        let id = calendar.calendarIdentifier
        try store.removeCalendar(calendar, commit: true)
        return ["id": id]
    case "list-reminders":
        let calendar = findReminderCalendar(store, id: string(payload, "reminders_list_id"), name: string(payload, "list_name"))
        let calendars = calendar.map { [$0] }
        let completed = bool(payload, "completed")
        let predicate = completed ? store.predicateForCompletedReminders(withCompletionDateStarting: nil, ending: nil, calendars: calendars) : store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: calendars)
        let limit = max(1, min(int(payload, "limit", default: 20), 100))
        return Array(try fetchReminders(store, predicate: predicate).prefix(limit)).map(reminderRow)
    case "create":
        let reminder = EKReminder(eventStore: store)
        reminder.title = string(payload, "title") ?? ""
        reminder.notes = string(payload, "notes")
        reminder.priority = max(0, min(int(payload, "priority", default: 0), 9))
        guard let calendar = findReminderCalendar(store, id: string(payload, "reminders_list_id"), name: string(payload, "list_name")) else {
            throw HelperError(code: "not_found", message: "Reminder list not found", recoverable: false)
        }
        if !calendar.allowsContentModifications {
            throw HelperError(code: "not_writable", message: "Reminder list is not writable", recoverable: false)
        }
        reminder.calendar = calendar
        if let dueText = string(payload, "due"), !dueText.isEmpty {
            let due = try parseDate(dueText)
            reminder.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second], from: due)
        }
        try store.save(reminder, commit: true)
        return ["id": reminder.calendarItemIdentifier]
    case "update":
        guard let reminder = try fetchReminders(store, predicate: store.predicateForReminders(in: nil)).first(where: { $0.calendarItemIdentifier == string(payload, "reminder_id") }) else {
            throw HelperError(code: "not_found", message: "Reminder not found", recoverable: false)
        }
        if let title = string(payload, "title") { reminder.title = title }
        if bool(payload, "clear_notes") { reminder.notes = nil } else if let notes = string(payload, "notes") { reminder.notes = notes }
        if bool(payload, "clear_due") {
            reminder.dueDateComponents = nil
        } else if let dueText = string(payload, "due"), !dueText.isEmpty {
            let due = try parseDate(dueText)
            reminder.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second], from: due)
        }
        if payload.keys.contains("priority") { reminder.priority = max(0, min(int(payload, "priority", default: reminder.priority), 9)) }
        try store.save(reminder, commit: true)
        return ["id": reminder.calendarItemIdentifier]
    case "search":
        let query = (string(payload, "query") ?? "").lowercased()
        let limit = max(1, min(int(payload, "limit", default: 50), 200))
        let includeCompleted = bool(payload, "include_completed")
        let predicate = includeCompleted ? store.predicateForReminders(in: nil) : store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: nil)
        return Array(try fetchReminders(store, predicate: predicate).filter { reminder in
            if query.isEmpty { return true }
            if (reminder.title ?? "").lowercased().contains(query) { return true }
            if (reminder.notes ?? "").lowercased().contains(query) { return true }
            return false
        }.prefix(limit)).map(reminderRow)
    case "complete":
        guard let reminder = try fetchReminders(store, predicate: store.predicateForReminders(in: nil)).first(where: { $0.calendarItemIdentifier == string(payload, "reminder_id") }) else {
            throw HelperError(code: "not_found", message: "Reminder not found", recoverable: false)
        }
        reminder.isCompleted = true
        reminder.completionDate = Date()
        try store.save(reminder, commit: true)
        return ["id": reminder.calendarItemIdentifier]
    case "delete":
        guard let reminder = try fetchReminders(store, predicate: store.predicateForReminders(in: nil)).first(where: { $0.calendarItemIdentifier == string(payload, "reminder_id") }) else {
            throw HelperError(code: "not_found", message: "Reminder not found", recoverable: false)
        }
        try store.remove(reminder, commit: true)
        return ["id": string(payload, "reminder_id") ?? reminder.calendarItemIdentifier]
    default:
        throw HelperError(code: "invalid_operation", message: "Unsupported reminders operation", recoverable: false)
    }
}

let contactKeys: [CNKeyDescriptor] = [
    CNContactIdentifierKey as CNKeyDescriptor,
    CNContactGivenNameKey as CNKeyDescriptor,
    CNContactFamilyNameKey as CNKeyDescriptor,
    CNContactOrganizationNameKey as CNKeyDescriptor,
    CNContactEmailAddressesKey as CNKeyDescriptor,
    CNContactPhoneNumbersKey as CNKeyDescriptor,
    CNContactPostalAddressesKey as CNKeyDescriptor,
    CNContactBirthdayKey as CNKeyDescriptor,
    CNContactNoteKey as CNKeyDescriptor,
]

func labeled(_ values: [CNLabeledValue<NSString>]) -> [JSON] {
    values.map { ["label": CNLabeledValue<NSString>.localizedString(forLabel: $0.label ?? ""), "value": $0.value as String] }
}

func labeledPhones(_ values: [CNLabeledValue<CNPhoneNumber>]) -> [JSON] {
    values.map { ["label": CNLabeledValue<CNPhoneNumber>.localizedString(forLabel: $0.label ?? ""), "value": $0.value.stringValue] }
}

func contactGroups(_ store: CNContactStore, _ contact: CNContact) -> [String] {
    (try? store.groups(matching: nil).compactMap { group in
        let predicate = CNContact.predicateForContactsInGroup(withIdentifier: group.identifier)
        let contacts = (try? store.unifiedContacts(matching: predicate, keysToFetch: [CNContactIdentifierKey as CNKeyDescriptor])) ?? []
        return contacts.contains(where: { $0.identifier == contact.identifier }) ? group.name : nil
    }) ?? []
}

func contactRow(_ store: CNContactStore, _ contact: CNContact, includeDetails: Bool) -> JSON {
    let emails = labeled(contact.emailAddresses)
    let phones = labeledPhones(contact.phoneNumbers)
    var row: JSON = [
        "id": contact.identifier,
        "first": contact.givenName,
        "last": contact.familyName,
        "email": (emails.first?["value"] as? String) ?? NSNull(),
        "phone": (phones.first?["value"] as? String) ?? NSNull(),
        "company": contact.organizationName,
        "emails": emails,
        "phones": phones,
        "groups": contactGroups(store, contact),
    ]
    if includeDetails {
        row["addresses"] = contact.postalAddresses.map { CNPostalAddressFormatter.string(from: $0.value, style: .mailingAddress) }
        if let birthday = contact.birthday, let date = Calendar.current.date(from: birthday) {
            row["birthday"] = emitDate(date)
        } else {
            row["birthday"] = NSNull()
        }
        row["notes"] = contact.note
    }
    return row
}

func contactBirthdayDate(_ contact: CNContact, year: Int) -> Date? {
    guard var components = contact.birthday else { return nil }
    components.year = year
    return Calendar.current.date(from: components)
}

func contactBirthdayRow(_ store: CNContactStore, _ contact: CNContact, year: Int) -> JSON? {
    guard let date = contactBirthdayDate(contact, year: year) else { return nil }
    var row = contactRow(store, contact, includeDetails: false)
    row["birthday"] = emitDate(date)
    return row
}

func contactMatches(_ contact: CNContact, _ query: String) -> Bool {
    if query.isEmpty { return true }
    let q = query.lowercased()
    if contact.givenName.lowercased().contains(q) || contact.familyName.lowercased().contains(q) || contact.organizationName.lowercased().contains(q) {
        return true
    }
    if "\(contact.givenName) \(contact.familyName)".lowercased().contains(q) { return true }
    if contact.emailAddresses.contains(where: { ($0.value as String).lowercased().contains(q) }) { return true }
    if contact.phoneNumbers.contains(where: { $0.value.stringValue.lowercased().contains(q) }) { return true }
    return false
}

func fetchContacts(_ store: CNContactStore, group: String?) throws -> [CNContact] {
    if let group, !group.isEmpty {
        let groups = try store.groups(matching: nil).filter { $0.name.caseInsensitiveCompare(group) == .orderedSame || $0.identifier == group }
        guard let matched = groups.first else { return [] }
        return try store.unifiedContacts(matching: CNContact.predicateForContactsInGroup(withIdentifier: matched.identifier), keysToFetch: contactKeys)
    }
    var contacts: [CNContact] = []
    let request = CNContactFetchRequest(keysToFetch: contactKeys)
    try store.enumerateContacts(with: request) { contact, _ in
        contacts.append(contact)
    }
    return contacts
}

func handleContacts(_ operation: String, _ payload: JSON) throws -> Any {
    if operation == "health" { return ["status": "ok"] }
    let store = CNContactStore()
    try requireContactsAccess(store)

    switch operation {
    case "search":
        let query = string(payload, "query") ?? ""
        let limit = max(1, min(int(payload, "limit", default: 10), 50))
        return try fetchContacts(store, group: string(payload, "group")).filter { contactMatches($0, query) }.prefix(limit).map { contactRow(store, $0, includeDetails: false) }
    case "get":
        guard let id = string(payload, "contact_id") else {
            throw HelperError(code: "invalid_input", message: "Missing contact id", recoverable: false)
        }
        let contacts = try store.unifiedContacts(matching: CNContact.predicateForContacts(withIdentifiers: [id]), keysToFetch: contactKeys)
        guard let contact = contacts.first else {
            throw HelperError(code: "not_found", message: "Contact not found", recoverable: false)
        }
        return contactRow(store, contact, includeDetails: true)
    case "create":
        let contact = CNMutableContact()
        contact.givenName = string(payload, "first") ?? ""
        contact.familyName = string(payload, "last") ?? ""
        contact.organizationName = string(payload, "company") ?? ""
        if let email = string(payload, "email") { contact.emailAddresses = [CNLabeledValue(label: CNLabelWork, value: email as NSString)] }
        if let phone = string(payload, "phone") { contact.phoneNumbers = [CNLabeledValue(label: CNLabelPhoneNumberMobile, value: CNPhoneNumber(stringValue: phone))] }
        let request = CNSaveRequest()
        request.add(contact, toContainerWithIdentifier: nil)
        try store.execute(request)
        return ["id": contact.identifier]
    case "update":
        guard let id = string(payload, "contact_id") else {
            throw HelperError(code: "invalid_input", message: "Missing contact id", recoverable: false)
        }
        let contacts = try store.unifiedContacts(matching: CNContact.predicateForContacts(withIdentifiers: [id]), keysToFetch: contactKeys)
        guard let existing = contacts.first else {
            throw HelperError(code: "not_found", message: "Contact not found", recoverable: false)
        }
        let contact = existing.mutableCopy() as! CNMutableContact
        if let first = string(payload, "first") { contact.givenName = first }
        if let last = string(payload, "last") { contact.familyName = last }
        if let company = string(payload, "company") { contact.organizationName = company }
        if let email = string(payload, "email") { contact.emailAddresses = [CNLabeledValue(label: CNLabelWork, value: email as NSString)] }
        if let phone = string(payload, "phone") { contact.phoneNumbers = [CNLabeledValue(label: CNLabelPhoneNumberMobile, value: CNPhoneNumber(stringValue: phone))] }
        let request = CNSaveRequest()
        request.update(contact)
        try store.execute(request)
        return ["id": contact.identifier]
    case "delete":
        guard let id = string(payload, "contact_id") else {
            throw HelperError(code: "invalid_input", message: "Missing contact id", recoverable: false)
        }
        let contacts = try store.unifiedContacts(matching: CNContact.predicateForContacts(withIdentifiers: [id]), keysToFetch: contactKeys)
        guard let existing = contacts.first else {
            throw HelperError(code: "not_found", message: "Contact not found", recoverable: false)
        }
        let request = CNSaveRequest()
        request.delete(existing.mutableCopy() as! CNMutableContact)
        try store.execute(request)
        return ["id": id]
    case "birthdays":
        let mode = string(payload, "mode") ?? "upcoming"
        let days = max(1, min(int(payload, "days", default: 30), 366))
        let now = Date()
        let calendar = Calendar.current
        let todayStart = calendar.startOfDay(for: now)
        let end = calendar.date(byAdding: .day, value: days, to: todayStart) ?? todayStart
        let thisYear = calendar.component(.year, from: todayStart)
        return try fetchContacts(store, group: nil).compactMap { contact -> JSON? in
            let dates = [thisYear, thisYear + 1].compactMap { contactBirthdayDate(contact, year: $0) }
            guard let birthday = dates.first(where: { $0 >= todayStart && $0 < end }) else { return nil }
            if mode == "today" && !calendar.isDate(birthday, inSameDayAs: todayStart) { return nil }
            var row = contactRow(store, contact, includeDetails: false)
            row["birthday"] = emitDate(birthday)
            return row
        }
    case "list-groups":
        return try store.groups(matching: nil).map { group in
            [
                "id": group.identifier,
                "name": group.name,
                "kind": "contact_group",
                "account_name": NSNull(),
                "path": NSNull(),
                "writable": NSNull(),
                "default_candidate": false,
            ] as JSON
        }
    default:
        throw HelperError(code: "invalid_operation", message: "Unsupported contacts operation", recoverable: false)
    }
}

func dispatch(domain: String, operation: String, payload: JSON) throws -> Any {
    if domain == "health" { return ["status": "ok"] }
    switch domain {
    case "calendar": return try handleCalendar(operation, payload)
    case "reminders": return try handleReminders(operation, payload)
    case "contacts": return try handleContacts(operation, payload)
    default: throw HelperError(code: "invalid_domain", message: "Unsupported native domain", recoverable: false)
    }
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    writeJSON(failure("invalid_input", "Usage: apple-ecosystem-helper <domain> <operation>", recoverable: false))
    exit(2)
}

do {
    let payload = try readPayload()
    let result = try dispatch(domain: args[1], operation: args[2], payload: payload)
    writeJSON(success(result))
} catch let error as HelperError {
    writeJSON(failure(error.code, error.message, recoverable: error.recoverable))
    exit(1)
} catch {
    writeJSON(failure("native_backend_error", error.localizedDescription, recoverable: true))
    exit(1)
}
