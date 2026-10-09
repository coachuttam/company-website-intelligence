"""B-96: the label files the scoring scripts name exist in the folders they read from.
Checks names and existence only; no label is scored and no model call is made."""
from eval.baseline import DEV_LABEL_DIR, DEV_SET
from eval.held_out import HELD_OUT_LABEL_DIR, HELD_OUT_LABELS


def test_every_dev_set_label_exists_under_the_dev_label_dir():
    missing = [lf for lf, _ in DEV_SET if not (DEV_LABEL_DIR / lf).is_file()]
    assert DEV_LABEL_DIR.name == "dev" and not missing, missing


def test_every_old_held_out_label_exists_under_the_archived_v1_dir():
    missing = [lf for lf, _ in HELD_OUT_LABELS if not (HELD_OUT_LABEL_DIR / lf).is_file()]
    assert HELD_OUT_LABEL_DIR.name == "heldout_v1_archived" and not missing, missing
