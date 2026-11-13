import UIKit

/// Single SCCS identity for the visible installed build.
enum RoomTrekBuild {
    static let sccsID = "@(#)AppDelegate.swift 3.2.imu.1 2026/11/12 15:12:06"
    static var headline: String {
        "RoomTrek " + sccsID.split(separator: " ").dropFirst().joined(separator: " ")
    }
}

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
