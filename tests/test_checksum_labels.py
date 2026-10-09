"""eval/checksum_labels.py: --verify passes on unmodified label files and fails on a modified one.
Temp files only; the real v2 labels are never read or written."""
import json

from eval.checksum_labels import verify, write


def test_verify_passes_unmodified_and_fails_modified(tmp_path):
    names = ["a.json", "b.json"]
    for n in names:
        (tmp_path / n).write_text(json.dumps({"labeling_metadata": {"company_name": "Acme",
                                  "date_labeled": "2026-10-10"}, "fields": {}}))
    sums = tmp_path / "labels.sha256"
    assert write(tmp_path, sums, names)[0] and verify(tmp_path, sums, names)[0]
    (tmp_path / "b.json").write_text((tmp_path / "b.json").read_text() + " ")
    assert not verify(tmp_path, sums, names)[0]


def test_v2_files_are_found_by_split_not_by_a_fixed_list(tmp_path):
    from eval.checksum_labels import v2_label_files
    for name, split in [("a.json", "held_out_v2"), ("b.json", "held_out_v2"), ("c.json", "dev"),
                        ("_template_v2.json", "held_out_v2")]:
        (tmp_path / name).write_text(json.dumps({"labeling_metadata": {"split": split}}))
    assert v2_label_files(tmp_path) == ["a.json", "b.json"]


def test_write_refuses_unlabelled_template_files(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"labeling_metadata": {"company_name": "",
                                     "date_labeled": "YYYY-MM-DD", "split": "held_out_v2"}}))
    sums = tmp_path / "labels.sha256"
    ok, message = write(tmp_path, sums)
    assert not ok and "still unlabelled" in message and not sums.exists()
