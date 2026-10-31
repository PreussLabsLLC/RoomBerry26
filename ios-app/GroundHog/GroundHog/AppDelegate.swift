// @(#)AppDelegate.swift 3.1 2026/10/31 11:30:00
import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let w = UIWindow(frame: UIScreen.main.bounds)
        w.rootViewController = GroundHogViewController()
        w.makeKeyAndVisible(); window = w
        return true
    }
}
