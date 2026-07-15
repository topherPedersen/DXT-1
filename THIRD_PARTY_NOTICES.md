# Third-Party Software and Assets

The PolyForm Noncommercial License in `LICENSE.md` applies only to original
DXT-1 code and materials for which the DXT-1 licensor owns the relevant rights.
It does not replace, restrict, expand, or relicense third-party components.
Each third-party component remains governed by its own terms.

## ADTOF and ADTOF-PyTorch

DXT-1 is highly dependent on
[ADTOF-PyTorch](https://github.com/xavriley/ADTOF-pytorch) for drum
transcription. ADTOF-PyTorch describes itself as a PyTorch port of the original
[ADTOF](https://github.com/MZehren/ADTOF), reimplements portions of that system,
converts its officially released weights, and bundles model weights.

The original ADTOF repository states that its contents are licensed under
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/).
That noncommercial dependency is the principal reason DXT-1 uses a
software-oriented noncommercial source-available license rather than a
permissive open-source license such as MIT.

As of July 15, 2026, the ADTOF-PyTorch repository has no published `LICENSE`
file and its installed package declares no license. Absence of a license does
not grant permission to copy, modify, or redistribute code or bundled weights.
Before publicly distributing DXT-1 together with ADTOF-PyTorch, or relying on
it for any commercial or public production use, obtain clarification or
permission from the relevant rights holders. DXT-1's license cannot cure or
expand those third-party rights.

## Direct Python dependencies

| Component | Role | Upstream license |
| --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | Web framework | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI server | BSD 3-Clause |
| [python-multipart](https://github.com/Kludex/python-multipart) | Upload parsing | Apache License 2.0 |
| [Mido](https://github.com/mido/mido) | MIDI processing | MIT |
| [Demucs](https://github.com/facebookresearch/demucs) | Drum-stem separation | MIT |
| [ADTOF-PyTorch](https://github.com/xavriley/ADTOF-pytorch) | Drum transcription | No license published; see above |

ADTOF-PyTorch directly depends on PyTorch (BSD 3-Clause), librosa (ISC),
pretty-midi (MIT), and NumPy (BSD 3-Clause). Demucs and the web stack install
additional transitive packages. Those packages are not covered by DXT-1's
license; consult the license files installed with each package and preserve
all required copyright, attribution, notice, and source-offer materials when
redistributing an environment or application bundle.

Because `requirements.txt` permits dependency updates, the transitive package
set can change over time. A production release should lock exact versions and
generate a complete software-bill-of-materials and license report from the
actual release environment.

## Fonts

- **Boecklins Universe**, copyright 2013 Peter Wiegel, is distributed under
  the SIL Open Font License 1.1. The required license text is included at
  `licenses/OFL-1.1.txt`.
- **Aileron**, designed by Sora Sagano, is published under CC0 1.0 Universal.
  See https://creativecommons.org/publicdomain/zero/1.0/.

## User-supplied audio

DXT-1 does not grant users any rights in uploaded music. Users are responsible
for having permission to upload, process, and download material, and for
complying with copyright and other applicable laws.
