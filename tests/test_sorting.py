import os
import unittest

from wagom_player import main_window


class WindowsLogicalKeyTest(unittest.TestCase):
    def test_observed_video_extensions_are_supported(self):
        observed_video_extensions = {
            ".mp4",
            ".mov",
            ".avi",
            ".3gp",
            ".mpg",
            ".wmv",
            ".mkv",
            ".flv",
            ".rmvb",
            ".asf",
            ".mpeg",
            ".webm",
            ".rm",
            ".m4v",
            ".m2ts",
            ".ts",
            ".vob",
            ".3g2",
        }

        self.assertTrue(
            observed_video_extensions.issubset(main_window.SUPPORTED_VIDEO_EXTENSIONS)
        )

    def test_fallback_key_prefers_case_insensitive_natural_order(self):
        key = main_window._create_windows_logical_key(None)

        files = [
            "/tmp/File10.mp4",
            "/tmp/file2.mp4",
            "/tmp/file-3.mp4",
            "/tmp/File1.mp4",
        ]

        expected = ["File1.mp4", "file2.mp4", "File10.mp4", "file-3.mp4"]
        sorted_files = sorted(files, key=key)

        self.assertEqual(expected, [os.path.basename(p) for p in sorted_files])

    def test_cmp_to_key_path_uses_basename_and_comparer(self):
        calls = []

        def fake_comparer(a: str, b: str) -> int:
            calls.append((a, b))
            return -1 if a < b else (1 if a > b else 0)

        key = main_window._create_windows_logical_key(fake_comparer)
        files = ["/tmp/b.mp4", "/tmp/A.mp4"]

        sorted(files, key=key)

        compared_names = {name for call in calls for name in call}
        self.assertEqual({"A.mp4", "b.mp4"}, compared_names)


if __name__ == "__main__":
    unittest.main()
