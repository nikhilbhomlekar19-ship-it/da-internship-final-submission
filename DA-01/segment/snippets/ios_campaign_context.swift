// iOS: attach the campaign that opened the app (deep link / MMP / push) so Segment sessions can be attributed.
import Segment

func trackAppOpened(source: String, medium: String, campaign: String) {
    Analytics.shared().track("Application Opened",
                             properties: ["from_background": false],
                             options: ["context": ["campaign": ["source": source, "medium": medium, "name": campaign]]])
}
