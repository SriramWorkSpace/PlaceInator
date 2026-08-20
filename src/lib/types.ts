/**
 * Wire types, mirrored field-for-field from the backend Pydantic schemas:
 * placeinator/profile/schemas.py, placeinator/api/{resumes,jobs,matching}.py.
 * Keep these in sync by hand until M1's follow-up generates them from the
 * OpenAPI schema (see docs/architecture.md's module map).
 */

export type WorkMode = "remote" | "hybrid" | "onsite" | "any";

export interface PreferencesIn {
  target_roles: string[];
  preferred_industries: string[];
  preferred_locations: string[];
  work_mode: WorkMode;
  min_salary: number | null;
  preferred_salary_min: number | null;
  preferred_salary_max: number | null;
  currency: string;
  willing_to_relocate: boolean;
  target_experience_years: number | null;
  accepts_fixed_term: boolean;
  max_contract_months: number | null;
  accepts_service_bond: boolean;
  max_bond_months: number | null;
  other_restrictions: string | null;
  /** Minimum overall match score (0..1) for a job to surface as a
   * personalized notification -- the Settings page's Notifications control. */
  notification_threshold: number;
}

export const DEFAULT_PREFERENCES: PreferencesIn = {
  target_roles: [],
  preferred_industries: [],
  preferred_locations: [],
  work_mode: "any",
  min_salary: null,
  preferred_salary_min: null,
  preferred_salary_max: null,
  currency: "INR",
  willing_to_relocate: true,
  target_experience_years: null,
  accepts_fixed_term: true,
  max_contract_months: null,
  accepts_service_bond: true,
  max_bond_months: null,
  other_restrictions: null,
  notification_threshold: 0.6,
};

export interface ProfileIn {
  full_name: string;
  email: string;
  phone: string | null;
  college: string | null;
  department: string | null;
  student_id: string | null;
  name_aliases: string[];
  preferences: PreferencesIn;
}

export interface ProfileOut extends ProfileIn {
  id: number;
  onboarded: boolean;
}

export const SOURCE_FORMATS = ["pdf", "docx", "tex"] as const;
export type SourceFormat = (typeof SOURCE_FORMATS)[number];

export interface ResumeOut {
  id: number;
  label: string;
  target_role: string | null;
  version: number;
  job_category: string | null;
  source_format: string;
  chunk_count: number;
  is_primary: boolean;
}

/** Best-effort autofill preview parsed from an uploaded resume, before any
 * profile exists -- every field is independently nullable. */
export interface ExtractedProfileFields {
  full_name: string | null;
  email: string | null;
  phone: string | null;
  college: string | null;
  department: string | null;
}

export interface ManualJobIn {
  company: string;
  designation: string;
  description: string;
  location: string | null;
  url: string | null;
  /** ISO date string ("YYYY-MM-DD"), or null. */
  deadline: string | null;
}

export const JD_SOURCE_FORMATS = ["pdf", "docx"] as const;
export type JdSourceFormat = (typeof JD_SOURCE_FORMATS)[number];

export const JOB_SEARCH_SOURCES = ["indeed", "linkedin", "naukri"] as const;
export type JobSearchSource = (typeof JOB_SEARCH_SOURCES)[number];

export interface JobSearchIn {
  source: JobSearchSource;
  keywords: string;
  location?: string;
}

export interface JobSearchOut {
  jobs: JobOut[];
  /** Set, and jobs empty, when the source's own access-control boundary was
   * hit (ADR 0003) -- expected and common for linkedin/naukri, not an error. */
  blocked_reason: string | null;
}

/** Best-effort autofill preview parsed from an uploaded JD file -- designation
 * and company are frequently null (a JD's layout is far less standardized
 * than a resume's), but description is always the full parsed text. */
export interface ExtractedJobFields {
  designation: string | null;
  company: string | null;
  description: string;
}

export interface JobOut {
  id: number;
  source: string;
  company: string;
  designation: string;
  location: string | null;
  deadline: string | null;
  required_skill_ids: string[];
  preferred_skill_ids: string[];
  /** Hard-constraint verdict (spec §2). Set means excluded, but the job is
   * still returned -- never hidden -- so the UI can explain why. */
  filtered_out_reason: string | null;
}

/** One job's place in the personalized ranking (spec §2's Personalized Job
 * Ranking) -- combines the semantic match against the primary resume with
 * the soft-preference signal. */
export interface JobRanking {
  job: JobOut;
  /** Null when there's no primary resume to score against. */
  semantic_score: number | null;
  soft_preference_score: number;
  soft_preference_reasons: string[];
  overall_score: number;
}

export interface ComponentScore {
  value: number;
  weight: number;
  evidence: { resume_text: string; requirement_text: string; similarity: number }[];
}

export type MatchExplanation = Record<
  "overall" | "skills" | "projects" | "experience" | "role",
  ComponentScore
>;

export interface MatchOut {
  resume_id: number;
  resume_label: string;
  semantic_score: number;
  personalized_score: number;
  explanation: MatchExplanation;
}
