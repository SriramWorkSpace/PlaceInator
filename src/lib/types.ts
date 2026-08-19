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
}

export interface ManualJobIn {
  company: string;
  designation: string;
  description: string;
  location: string | null;
  url: string | null;
}

export interface JobOut {
  id: number;
  source: string;
  company: string;
  designation: string;
  location: string | null;
  required_skill_ids: string[];
  preferred_skill_ids: string[];
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
