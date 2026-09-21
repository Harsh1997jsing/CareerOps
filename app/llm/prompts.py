"""Prompt templates for Claude LLM calls across the CareerOps pipeline.

Contains prompt templates for:
- `JOB_FIT_ANALYSIS_PROMPT`: Evaluates job postings against candidate skills,
  evidence, and constraints.
- `RESUME_SECTION_PROMPT`: Drafts targeted resume sections grounded in candidate
  evidence entries without inventing claims or echoing job descriptions verbatim.
- `COVER_LETTER_PROMPT`: Generates cover letters reflecting candidate voice samples
  and evidence.
- `CLAIM_CHECK_PROMPT`: Fact-checks generated documents strictly against candidate
  evidence IDs to block unsupported claims.
- `CHAT_SEARCH_INTENT_PROMPT`: Extracts job-search filters from a chat message.
- `CHAT_RESULT_SUMMARY_PROMPT`: Writes one-line summaries for a batch of
  staged search results in a single call.
- `RESUME_EDIT_PROMPT` / `COVER_LETTER_EDIT_PROMPT`: Revise an
  already-generated document from user feedback, one call, whole
  document at once (not per-section) — for the suggest-then-confirm
  document editing flow.
"""

JOB_FIT_ANALYSIS_PROMPT = """You are analyzing whether a candidate is a good fit for a job.
Only use information given below. Never invent skills, experience, or metrics
that are not present in the candidate's evidence.

JOB DESCRIPTION:
{job_description}

CANDIDATE SKILLS:
{skills_yaml}

CANDIDATE EXPERIENCE / EVIDENCE:
{evidence_yaml}

CANDIDATE CONSTRAINTS:
{constraints_yaml}

Analyze the fit. Be honest about gaps — do not inflate the fit score to be
encouraging. A missing required skill should lower the score and confidence,
and be listed in missing_requirements.
"""

RESUME_SECTION_PROMPT = """You are writing the "{section}" section of a resume.
Use ONLY information present in CANDIDATE EVIDENCE below. Never invent
skills, experience, metrics, companies, dates, or achievements that are not
directly supported by an evidence entry. Every fact you use must come from
an evidence entry — record its id in evidence_ids_used.

Write for a human reader first. Do not copy the job description's exact
wording — describe the candidate's own experience in the candidate's own
terms, even where the underlying skill overlaps with what the job asks for.

JOB DESCRIPTION:
{job_description}

CANDIDATE SKILLS:
{skills_yaml}

CANDIDATE EVIDENCE:
{evidence_yaml}

Write only the "{section}" section content. If the evidence does not support
a strong "{section}" section for this job, write a shorter, honest one rather
than padding it with unsupported claims.
"""

COVER_LETTER_PROMPT = """You are writing a cover letter for this candidate, as
the candidate, in their own voice. Use ONLY information present in CANDIDATE
EVIDENCE below — never invent skills, experience, metrics, or achievements
that are not directly supported by an evidence entry. Record the evidence
ids you used in evidence_ids_used.

Reference the job's actual requirements and specific pieces of candidate
evidence — avoid generic, could-apply-to-any-job filler. Target a length of
{min_words}-{max_words} words.

Match the tone, sentence rhythm, and vocabulary of the VOICE SAMPLES below —
these are the candidate's own past writing. Do not copy their content or
subject matter, only the way they write.

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
{profile_yaml}

CANDIDATE EVIDENCE:
{evidence_yaml}

VOICE SAMPLES (style reference only):
{voice_samples}
"""

CLAIM_CHECK_PROMPT = """You are a fact-checker. Compare each claim in the
GENERATED TEXT below against the EVIDENCE list. For every factual claim
(company names, titles, dates, technologies, metrics, achievements),
determine whether it is directly supported by an evidence ID.

If a claim has no matching evidence_id, mark it unverified and list it
in blocking_claims. Do not be lenient — an unverified claim should block
the application, even if it seems plausible.

GENERATED TEXT:
{generated_text}

EVIDENCE:
{evidence_yaml}
"""

CHAT_SEARCH_INTENT_PROMPT = """You are the search assistant for CareerOps, a job
search tool. Extract structured job-search filters from the user's message below.

FILTERS ALREADY CONFIRMED EARLIER IN THIS CONVERSATION (carry these forward
unless this message changes them):
{known_filters}

USER MESSAGE:
{message}

Extract:
- query: job title/role/keywords to search for (combine with any query
  already confirmed above if this message only adds detail to it).
- location, experience, posted_within_days, company: set only if mentioned
  in this message or already confirmed above.
- sources: pick from "explore" (broad multi-source search, the default),
  "scrape" (a direct multi-site scrape — pick this when the user names a
  specific site like Indeed/Naukri/Glassdoor, or explicitly says
  "scrape"), "targets" (the user's own tracked company list — pick this
  when the message is about a specific company on their target list, or
  says "my target companies"). Default to ["explore"] alone unless the
  message clearly implies otherwise; include more than one if it implies
  more than one.
- ready_to_search: true once there's a usable `query` — location,
  experience, company, posted_within_days, and sources are optional
  narrowing filters, never required to run a search.
- clarification_question: set only if `query` is still missing or too
  vague to search on at all (e.g. "find me a job"); ask ONE short,
  specific question. Leave it null once ready_to_search is true.

Never invent a filter value that wasn't stated.
"""

CHAT_RESULT_SUMMARY_PROMPT = """You are summarizing job search results for
CareerOps. For each numbered posting below, write ONE short sentence (under
20 words) capturing the role, level, and any standout requirement — do not
just restate the title and company.

POSTINGS:
{listing}

Return exactly one summary per posting, indexed to match the numbers above.
"""

RESUME_EDIT_PROMPT = """You are revising an already-generated resume based on
the candidate's own feedback. Use ONLY information present in CANDIDATE
EVIDENCE below — never invent skills, experience, metrics, companies, dates,
or achievements that are not directly supported by an evidence entry, even
if the feedback seems to ask for something not backed by evidence (in that
case, note the limitation in change_summary instead of inventing a claim).

Apply ONLY what the feedback asks for — leave every other section's content
exactly as it is unless changing it is unavoidable (e.g. the feedback asks
to shorten the whole resume). Return the full section list either way
(write_resume_docx needs every section, not just the changed one).

JOB DESCRIPTION:
{job_description}

CANDIDATE EVIDENCE:
{evidence_yaml}

CURRENT RESUME SECTIONS:
{current_sections}

CANDIDATE FEEDBACK:
{feedback}

Return the revised sections plus a one-sentence change_summary describing
what you changed and why — specific enough that the candidate can decide
whether to accept it without re-reading the whole resume.
"""

COVER_LETTER_EDIT_PROMPT = """You are revising an already-generated cover
letter based on the candidate's own feedback. Use ONLY information present
in CANDIDATE EVIDENCE below — never invent skills, experience, metrics, or
achievements not directly supported by an evidence entry, even if the
feedback seems to ask for something not backed by evidence (in that case,
note the limitation in change_summary instead of inventing a claim).

Apply ONLY what the feedback asks for — preserve the rest of the letter's
content and voice unless the feedback requires a broader change.

JOB DESCRIPTION:
{job_description}

CANDIDATE EVIDENCE:
{evidence_yaml}

CURRENT COVER LETTER:
{current_content}

CANDIDATE FEEDBACK:
{feedback}

Return the full revised letter plus a one-sentence change_summary
describing what you changed and why.
"""
