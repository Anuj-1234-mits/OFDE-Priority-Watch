import json
import os
import unittest

from ofde.ingest import ImportErrorOFDE, build_dataset, parse_tle_text
from ofde.tle import with_checksum

L1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestIngest(unittest.TestCase):
    def test_three_line(self):
        acc, rej = parse_tle_text(f"ISS (ZARYA)\n{L1}\n{L2}\n")
        self.assertEqual((len(acc), len(rej)), (1, 0))
        self.assertEqual(acc[0]["tle"].name, "ISS (ZARYA)")

    def test_zero_prefixed_name(self):
        acc, _ = parse_tle_text(f"0 ISS\n{L1}\n{L2}")
        self.assertEqual(acc[0]["tle"].name, "ISS")

    def test_two_line_unknown_name(self):
        acc, _ = parse_tle_text(f"{L1}\n{L2}")
        self.assertIsNone(acc[0]["tle"].name)

    def test_empty_rejected(self):
        for t in ("", "   \n  "):
            with self.assertRaises(ImportErrorOFDE):
                parse_tle_text(t)

    def test_unpaired_line(self):
        acc, rej = parse_tle_text(L1 + "\n")
        self.assertEqual(len(acc), 0)
        self.assertEqual(rej[0]["issues"][0]["code"], "UNPAIRED_LINE")

    def test_name_without_elements(self):
        acc, rej = parse_tle_text(f"LONELY NAME\n{L1}\n{L2}\nANOTHER NAME\n")
        self.assertEqual(len(acc), 1)
        self.assertEqual(rej[0]["issues"][0]["code"], "NAME_WITHOUT_ELEMENTS")

    def test_partial_acceptance_and_error_detail(self):
        bad = L1[:68] + "0"
        txt = f"GOOD\n{L1}\n{L2}\nBAD\n{bad}\n{L2}\n"
        ds = build_dataset(txt, filename="x.tle", source_description="unit test", origin="manual")
        self.assertEqual(ds["validation"]["outcome"], "accepted_with_rejections")
        self.assertEqual((ds["validation"]["accepted"], ds["validation"]["rejected"]), (1, 1))
        self.assertIn("CHECKSUM_MISMATCH", [i["code"] for i in ds["rejected"][0]["issues"]])

    def test_all_rejected(self):
        ds = build_dataset(f"{L1[:68]}0\n{L2}\n", filename=None, source_description="s", origin="manual")
        self.assertEqual(ds["validation"]["outcome"], "rejected")
        self.assertEqual(ds["objects"], [])

    def test_original_text_preserved_verbatim(self):
        txt = f"ISS\r\n{L1}  \r\n{L2}\r\n"
        ds = build_dataset(txt, filename="iss.txt", source_description="s", origin="real")
        self.assertEqual(ds["original_text"], txt)
        self.assertTrue(any(i["code"] == "TRAILING_WHITESPACE_REMOVED" for i in ds["objects"][0]["issues"]))

    def test_unknown_is_none_not_zero_or_empty(self):
        ds = build_dataset(f"{L1}\n{L2}", filename=None, source_description="s", origin="manual")
        o = ds["objects"][0]
        self.assertIsNone(o["name"])
        self.assertIsNone(o["object_type"])

    def test_origin_and_source_required(self):
        with self.assertRaises(ImportErrorOFDE):
            build_dataset(f"{L1}\n{L2}", filename=None, source_description="s", origin="imaginary")
        with self.assertRaises(ImportErrorOFDE):
            build_dataset(f"{L1}\n{L2}", filename=None, source_description="  ", origin="manual")

    def test_duplicate_catalog_warns_and_keeps_both(self):
        ds = build_dataset(f"{L1}\n{L2}\n{L1}\n{L2}\n", filename=None, source_description="s", origin="manual")
        self.assertEqual([o["object_id"] for o in ds["objects"]], ["25544", "25544#2"])
        self.assertTrue(any(i["code"] == "DUPLICATE_CATALOG" for i in ds["objects"][1]["issues"]))

    def test_provenance_recorded(self):
        ds = build_dataset(f"{L1}\n{L2}", filename="f.tle", source_description="CelesTrak sample, hand-copied", origin="real")
        p = ds["objects"][0]["provenance"]
        self.assertEqual((p["origin"], p["filename"]), ("real", "f.tle"))
        self.assertIn("TEME", ds["units_frame_assumptions"])

    def test_demo_dataset_is_synthetic_and_valid(self):
        with open(os.path.join(ROOT, "data", "demo_synthetic.json"), encoding="utf-8") as fh:
            demo = json.load(fh)
        ds = build_dataset(demo["tle_text"], filename="demo", source_description=demo["source_description"], origin="synthetic",
                           object_metadata=demo["objects"], cases=demo["cases"])
        self.assertEqual(ds["validation"]["outcome"], "accepted")
        self.assertEqual(len(ds["objects"]), 4)
        self.assertEqual(len(ds["cases"]), 3)
        self.assertTrue(all("SYNTHETIC" in o["name"] for o in ds["objects"]))
        self.assertIn("SYNTHETIC", demo["source_description"])


if __name__ == "__main__":
    unittest.main()
