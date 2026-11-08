// @(#)AppDelegate.swift 3.1.roomtrek.2 2026/11/08 12:00:00
import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let w = UIWindow(frame: UIScreen.main.bounds)
        w.rootViewController = RoomTrekViewController()
        w.makeKeyAndVisible(); window = w
        return true
    }
}
