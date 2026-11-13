"""Speak qualified detector observations without claiming navigation success."""
# @(#)roomberry_scan_speech_test.py 3.2.scan.2 2026/11/10 13:25:00
import unittest
from unittest.mock import Mock
from roomberry_speech import SpeechSender, scan_announcement


def tag(tag_id=16, margin=100., hamming=0, error=.2, distance=400.):
    return dict(family='tag16h5', id=tag_id, decision_margin=margin, hamming=hamming,
                tag_pose_camera=dict(error=error), distance_mm=distance)


class ScanSpeechTest(unittest.TestCase):
    def test_clear_read_range_and_duplicate_weak_detection(self):
        text=scan_announcement(dict(tags=[tag(hamming=1,margin=1),tag()]), mapped_tags=[('tag16h5',16)])
        self.assertIn('tag 16, clear read',text)
        self.assertIn('Camera range 40 centimetres',text)
        self.assertEqual(text.count('tag 16'),1)

    def test_quality_labels_and_missing_metadata(self):
        self.assertIn('marginal read',scan_announcement(dict(tags=[tag(margin=15)])))
        self.assertIn('marginal read',scan_announcement(dict(tags=[tag(error=7)])))
        for row in [tag(margin=5),tag(hamming=1),tag(error=11)]:
            self.assertIn('No reliable tag',scan_announcement(dict(tags=[row])))
        self.assertIn('quality unavailable',scan_announcement(dict(tags=[dict(id=15)])))

    def test_configured_thresholds_and_mapping_preference(self):
        text=scan_announcement(dict(tags=[tag(16,margin=80),tag(28,margin=150)]),mapped_tags=[('tag16h5',16)])
        self.assertIn('tag 16',text);self.assertNotIn('tag 28',text)
        self.assertIn('unmapped tag 28',scan_announcement(dict(tags=[tag(28)]),mapped_tags=[('tag16h5',16)]))
        self.assertIn('No reliable tag',scan_announcement(dict(tags=[tag(margin=15)]),min_margin=20))

    def test_no_tag_skipped_error_and_unavailable_range(self):
        self.assertEqual(scan_announcement(dict(tags=[])),'No tags found, Captain.')
        self.assertIn('skipped while moving',scan_announcement(dict(detection_skipped=True)))
        self.assertIn('scan failed',scan_announcement(dict(detector_error='timeout')))
        self.assertNotIn('Camera range',scan_announcement(dict(tags=[tag(distance=float('nan'))])))

    def test_scan_results_queue_through_existing_speech_worker(self):
        sender=SpeechSender(b'key',5010,Mock(),scan_quality=dict(mapped_tags=[('tag16h5',16)]))
        command_id=sender.submit_scan_result(dict(tags=[tag()]))
        code,text,created,queued_id=sender._queue.get_nowait()
        self.assertEqual(code,'SCAN_RESULT');self.assertEqual(command_id,queued_id)
        self.assertIn('tag 16, clear read',text)
        self.assertEqual(sender.job_snapshot(command_id)['status'],'queued')


if __name__=='__main__':unittest.main()
