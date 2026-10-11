# Third-party notices

ADARE is licensed under the MIT License (see `LICENSE`), **except** for the files
listed here, which contain or depend on third-party material under other terms.

## NVIDIA LocateAnything (optional `grounding` extra)

- `adare/adare/backend/experiment/grounding/locate_server.py`

The model loading, GUI-grounding prompt builder and `<box>` output parser in this
file are adapted from NVIDIA's LocateAnything demo
(<https://huggingface.co/spaces/nvidia/LocateAnything>), which is published
without an open-source license. This file is therefore **not** covered by the
MIT License; its use is subject to NVIDIA's terms.

The model it loads, `nvidia/LocateAnything-3B`, is distributed under the NVIDIA
license at <https://huggingface.co/nvidia/LocateAnything-3B/blob/main/LICENSE>
(non-commercial). The weights are not part of this repository; they are
downloaded only when the opt-in `grounding` extra is used (`adare dev agent --ground`).

## Bundled documentation assets

- `docs/_static/` contains build output of the Furo Sphinx theme (MIT); see
  `docs/_static/scripts/furo.js.LICENSE.txt`.
