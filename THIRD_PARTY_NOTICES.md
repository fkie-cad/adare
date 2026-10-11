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

## RBCmd (bundled example tool)

- `adare/appdata/examples/experiments/win_deletefile/shared/tools/RBCmd.exe`
- `adare/appdata/examples/experiments/test_windows_admin/shared/tools/RBCmd.exe`

RBCmd, the Recycle Bin artifact parser by Eric Zimmerman
(<https://github.com/EricZimmerman/RBCmd>), is distributed under the MIT License,
Copyright (c) Eric R. Zimmerman. The binaries are included unmodified so the
example experiments run offline; `adare experiment create` downloads the same
tool from <https://download.ericzimmermanstools.com/RBCmd.zip>.
