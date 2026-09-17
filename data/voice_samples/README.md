# Voice samples

Drop 3-5 samples of your own past writing in here as `.txt` or `.md` files
before generating a cover letter — for example a LinkedIn post, a past cover
letter you wrote yourself, an email you're proud of, or a README intro.

`cover_letter.py` reads every `.txt`/`.md` file in this directory and gives
them to the model as a style reference only — it's told to match your tone,
sentence rhythm, and vocabulary, not to reuse their content or subject
matter. It needs at least one sample to run at all, and works best with
several so it isn't just imitating one specific piece.

You can leave this README in place — the loader skips any file named
`README` (case-insensitive) regardless of extension, so it won't be treated
as a voice sample.
