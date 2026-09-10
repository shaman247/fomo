import SwiftUI
import Combine
import AppIntents
import EventKit
import EventKitUI
import UserNotifications

struct SavedFomoSearch: Codable, Identifiable, AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Saved search")
    static let defaultQuery = SavedFomoSearchQuery()
    let id: String
    let title: String
    let url: URL
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(title)") }
}

struct SavedFomoSearchQuery: EntityQuery {
    @MainActor func entities(for identifiers: [String]) async throws -> [SavedFomoSearch] {
        SearchLibrary.shared.saved.filter { identifiers.contains($0.id) }
    }
    @MainActor func suggestedEntities() async throws -> [SavedFomoSearch] { SearchLibrary.shared.saved }
}

struct OpenSavedFomoSearchIntent: AppIntent {
    static let title: LocalizedStringResource = "Open saved search"
    static let openAppWhenRun = true
    @Parameter(title: "Search") var search: SavedFomoSearch
    @MainActor func perform() async throws -> some IntentResult {
        AssistantSearch.shared.presented = false
        AssistantSearch.shared.open(search.url)
        return .result()
    }
}

struct SelectedFomoOccurrence: Identifiable {
    let id: String
    let name: String
    let source: String
    let start: Date?
    let end: Date?
    let url: URL?
    let revision: String
}

@MainActor
final class SearchLibrary: ObservableObject {
    static let shared = SearchLibrary()
    @Published var saved: [SavedFomoSearch] = []
    @Published var reminders: [UNNotificationRequest] = []
    private let storageKey = "fomo.fixedSearches.v1"
    private init() {
        if let data = UserDefaults.standard.data(forKey: storageKey),
           let decoded = try? JSONDecoder().decode([SavedFomoSearch].self, from: data) {
            saved = decoded.filter { AssistantSearch.trusted($0.url) }
        }
    }
    private func persist() {
        if let data = try? JSONEncoder().encode(saved) { UserDefaults.standard.set(data, forKey: storageKey) }
        FomoShortcuts.updateAppShortcutParameters()
    }
    func save(title: String) async throws {
        let context = try await AssistantSearch.shared.call("get_context")
        guard let query = context["query"] as? [String: Any] else { throw LibraryError.noQuery }
        let link = try await AssistantSearch.shared.call("make_link", ["query": query])
        guard let value = link["url"] as? String, let url = URL(string: value), AssistantSearch.trusted(url) else { throw LibraryError.noQuery }
        saved.append(SavedFomoSearch(id: UUID().uuidString, title: String(title.prefix(100)), url: url))
        persist()
    }
    func remove(_ item: SavedFomoSearch) { saved.removeAll { $0.id == item.id }; persist() }
    func refreshReminders() async {
        reminders = await UNUserNotificationCenter.current().pendingNotificationRequests().filter { $0.identifier.hasPrefix("fomo.") }
    }
    func cancelReminder(_ id: String) {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [id])
        reminders.removeAll { $0.identifier == id }
    }
    func remind(_ occurrence: SelectedFomoOccurrence, at date: Date) async throws {
        guard date > Date() else { throw LibraryError.pastReminder }
        let center = UNUserNotificationCenter.current()
        guard try await center.requestAuthorization(options: [.alert, .sound]) else { throw LibraryError.notificationsDisabled }
        let content = UNMutableNotificationContent()
        content.title = occurrence.name
        content.body = "Saved event reminder. Event details may have changed; check the source before going."
        content.sound = .default
        content.userInfo = ["occurrenceKey": occurrence.id, "dataRevision": occurrence.revision, "source": occurrence.source]
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        var components = calendar.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date)
        components.timeZone = calendar.timeZone
        try await center.add(UNNotificationRequest(identifier: "fomo." + occurrence.id, content: content,
            trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: false)))
        await refreshReminders()
    }
}

enum LibraryError: LocalizedError {
    case noQuery, pastReminder, notificationsDisabled
    var errorDescription: String? {
        switch self {
        case .noQuery: "Apply a structured search on the map first."
        case .pastReminder: "Choose a reminder time in the future."
        case .notificationsDisabled: "Notifications are disabled. You can enable them in Settings."
        }
    }
}

struct SearchLibrarySections: View {
    @ObservedObject private var library = SearchLibrary.shared
    @State private var name = ""
    @State private var message = ""
    @State private var occurrences: [SelectedFomoOccurrence] = []
    @State private var selected: SelectedFomoOccurrence?
    @State private var cursor: String?
    var body: some View {
        Section("Saved searches") {
            Text("Saved searches keep their exact dates and area. They do not roll forward each day.").font(.caption).foregroundStyle(.secondary)
            TextField("Search name", text: $name)
            Button("Save current search") {
                Task { do { try await library.save(title: name); name = ""; message = "Search saved." } catch { message = error.localizedDescription } }
            }.disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            ForEach(library.saved) { item in
                HStack {
                    Button(item.title) { AssistantSearch.shared.presented = false; AssistantSearch.shared.open(item.url) }
                    Spacer()
                    Button(role: .destructive) { library.remove(item) } label: { Image(systemName: "trash") }.accessibilityLabel("Delete \(item.title)")
                }
            }
        }
        Section("Matching occurrences") {
            Button("Load current search results") { Task { await loadResults(more: false) } }
            ForEach(occurrences) { item in
                Button { selected = item } label: {
                    VStack(alignment: .leading) { Text(item.name); Text(item.source).font(.caption).foregroundStyle(.secondary) }
                }
            }
            if cursor != nil { Button("Load more") { Task { await loadResults(more: true) } } }
        }
        if !library.reminders.isEmpty {
            Section("Reminders") {
                Text("Reminders use cached event details and do not track schedule changes.").font(.caption).foregroundStyle(.secondary)
                ForEach(library.reminders, id: \.identifier) { reminder in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(reminder.content.title)
                            if let next = (reminder.trigger as? UNCalendarNotificationTrigger)?.nextTriggerDate() { Text(next, style: .date); Text(next, style: .time) }
                        }
                        Spacer()
                        Button("Cancel", role: .destructive) { library.cancelReminder(reminder.identifier) }
                    }
                }
            }
        }
        if !message.isEmpty { Section { Text(message) } }
        Section { Text("Saved searches and reminders are stored in this app. Calendar actions open Apple's editor for you to review and save.").font(.caption).foregroundStyle(.secondary) }
            .task { await library.refreshReminders() }
            .sheet(item: $selected) { OccurrenceActions(occurrence: $0) }
    }
    private func loadResults(more: Bool) async {
        do {
            var input: [String: Any] = ["limit": 25]
            if more, let cursor { input["cursor"] = cursor }
            let result = try await AssistantSearch.shared.call("get_current_results", input)
            let revision = (result["coverage"] as? [String: Any])?["revision"] as? String ?? ""
            var loaded: [SelectedFomoOccurrence] = []
            for event in result["items"] as? [[String: Any]] ?? [] {
                for o in event["occurrences"] as? [[String: Any]] ?? [] {
                    guard let key = o["key"] as? String else { continue }
                    let parts = (o["source"] as? [Any] ?? []).compactMap { $0 as? String }.filter { !$0.isEmpty }
                    let url = (event["urls"] as? [String])?.first.flatMap(URL.init(string:))
                    loaded.append(SelectedFomoOccurrence(id: key, name: event["name"] as? String ?? "Event", source: parts.joined(separator: " · "),
                        start: (o["start"] as? Double).map { Date(timeIntervalSince1970: $0 / 1000) },
                        end: (o["end"] as? Double).map { Date(timeIntervalSince1970: $0 / 1000) },
                        url: ["http", "https"].contains(url?.scheme ?? "") ? url : nil, revision: revision))
                }
            }
            occurrences = more ? occurrences + loaded : loaded
            cursor = result["cursor"] as? String
            message = occurrences.isEmpty ? "No matching occurrences. Apply a structured search first." : ""
        } catch { message = error.localizedDescription }
    }
}

struct OccurrenceActions: View {
    let occurrence: SelectedFomoOccurrence
    @State private var calendarPresented = false
    @State private var fireDate = Date()
    @State private var timeChosen = false
    @State private var message = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                Section { Text(occurrence.name); Text(occurrence.source); if let url = occurrence.url { Link("Check event source", destination: url) } }
                Section("Calendar") {
                    if occurrence.start != nil && occurrence.end != nil {
                        Button("Add to calendar…") { calendarPresented = true }
                    } else { Text("This occurrence does not have a confirmed start and end time.") }
                }
                Section("Reminder") {
                    Text("Choose an exact reminder time. This uses cached details; check the source for changes.")
                    DatePicker("Remind me at", selection: $fireDate, in: Date()..., displayedComponents: [.date, .hourAndMinute])
                        .onChange(of: fireDate) { timeChosen = true }
                    Button("Schedule reminder") { Task {
                        do { try await SearchLibrary.shared.remind(occurrence, at: fireDate); message = "Reminder scheduled." }
                        catch { message = error.localizedDescription }
                    } }.disabled(!timeChosen)
                    if !message.isEmpty { Text(message) }
                }
            }.navigationTitle("Event actions").toolbar { Button("Done") { dismiss() } }
        }.sheet(isPresented: $calendarPresented) { FomoCalendarEditor(occurrence: occurrence) }
    }
}

struct FomoCalendarEditor: UIViewControllerRepresentable {
    let occurrence: SelectedFomoOccurrence
    @Environment(\.dismiss) private var dismiss
    func makeCoordinator() -> Coordinator { Coordinator { dismiss() } }
    func makeUIViewController(context: Context) -> EKEventEditViewController {
        let controller = EKEventEditViewController()
        controller.eventStore = EKEventStore()
        let event = EKEvent(eventStore: controller.eventStore)
        event.title = occurrence.name; event.startDate = occurrence.start; event.endDate = occurrence.end
        event.url = occurrence.url
        event.notes = "Saved from Fomo. Check the source for schedule changes. Occurrence: \(occurrence.id)"
        controller.event = event; controller.editViewDelegate = context.coordinator
        return controller
    }
    func updateUIViewController(_ controller: EKEventEditViewController, context: Context) {}
    class Coordinator: NSObject, EKEventEditViewDelegate {
        let done: () -> Void
        init(done: @escaping () -> Void) { self.done = done }
        func eventEditViewController(_ controller: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) { done() }
    }
}
