# Audio fixtures

Checked-in `.wav` files land here in Unit 2 (`scripts/make-fixtures.py`
generates deterministic Hindi + English utterances). The mock Sarvam server
maps SHA-256(audio bytes) -> canned transcript, so e2e stays deterministic.
