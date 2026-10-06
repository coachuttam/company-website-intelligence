"""Optional decision layer (B-62): a classifier for fields whose answer is one of a few known
options, run AFTER extraction. Off by default (config.yaml classifier.provider: none). See
wi/classify/decisions.py for how a decision becomes a claim without bypassing the evidence gate.
"""
