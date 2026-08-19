# PlaceInator

## Project Overview

An intelligent placement assistant designed to help students discover suitable opportunities, match and restructure resumes, improve career readiness, personalize outreach, and automatically organize placement-cell communications.

The system is centered around three major capabilities:

1. **ML/NLP:** Resume ↔ Job semantic matching
2. **Document Intelligence:** JD + LaTeX Resume → tailored LaTeX Resume
3. **Placement Automation:** Gmail → placement documents → candidate detection → event extraction → Calendar

---

# 1. Candidate Profile & Preferences

The user's profile is the foundation for personalization.

### First-Time Onboarding

Collect:

- Personal details
- Education
- Skills
- Programming languages
- Frameworks
- Tools
- Projects
- Experience
- Certifications
- Achievements

### Career Preferences

- Target job roles
- Preferred industries
- Preferred locations
- Remote / hybrid / on-site preference
- Minimum expected salary
- Preferred salary range
- Willingness to relocate
- Target experience level

### Employment Constraints

- Willingness to accept fixed-term contracts
- Maximum acceptable contract duration
- Willingness to accept service bonds
- Maximum acceptable bond duration
- Other employment restrictions

### Profile Settings

All profile information and preferences can be edited later.

---

# 2. Personalized Job Intelligence

## Job Discovery

Find relevant job opportunities from supported sources.

Extract:

- Company
- Designation
- Location
- Salary
- Experience requirement
- Required skills
- Preferred skills
- Education requirements
- Work mode
- Job type
- Application deadline
- Job URL

## Job Filtering

Apply the user's preferences.

### Hard Constraints

Conditions that can eliminate a job.

Examples:

- Minimum salary
- Maximum acceptable bond duration
- Required experience range
- Unacceptable work location

### Soft Preferences

Conditions that influence ranking but do not necessarily eliminate a job.

Examples:

- Preferred city
- Preferred work mode
- Preferred industry

## Neural Resume ↔ Job Matching

Compare the semantic meaning of the user's resume and the job description.

The model evaluates relevance between:

- Overall resume and JD
- Skills and requirements
- Projects and responsibilities
- Experience and requirements
- Role and candidate profile

Output:

- Semantic match score
- Relevant resume
- Relevant resume components

## Personalized Job Ranking

Combine:

- Semantic match
- Skill match
- Role match
- Location preference
- Salary preference
- Experience match
- Employment-condition compatibility

Output:

> A personalized job score and ranked opportunity list.

## Personalized Job Notifications

Notify the user about opportunities that meet their preferences and match threshold.

Notifications should explain *why* the opportunity is relevant.

---

# 3. Resume Intelligence

## Resume Library

Allow multiple role-specific resumes.

Example:

```text
Resume Library
├── Software Engineer
├── Backend Engineer
├── Data Scientist
├── Frontend Developer
└── ML Engineer
```

Each resume can have:

- Target role
- Version
- Skills
- Date updated
- Associated job category

## Resume Parsing

Extract structured information from resumes:

- Skills
- Programming languages
- Frameworks
- Tools
- Projects
- Experience
- Education
- Certifications
- Achievements

## Resume Selection

For each job opportunity:

```text
Job
  ↓
Compare against all user resumes
  ↓
Calculate relevance
  ↓
Recommend the best-matching resume
```

Example:

```text
Backend Engineer

SDE Resume           93%
ML Resume            68%
Data Science Resume  61%
Frontend Resume       52%

Recommended: SDE Resume
```

The user can override the recommendation.

---

# 4. Career Skill Intelligence

## Skill Gap Analysis

Analyze the user's target jobs and identify commonly requested skills.

Compare:

```text
Target job market
       ↓
Required skills
       ↓
User's existing skills
       ↓
Missing / weak skills
```

## Skill Prioritization

Prioritize gaps based on:

- Frequency across target jobs
- Relevance to desired roles
- Importance to selected opportunities
- Current user skill coverage

## Improvement Recommendations

For each important skill gap, provide:

- Skill to learn
- Priority
- Why it matters
- Suggested learning direction/resources

---

# 5. JD-Based LaTeX Resume Tailoring

A standalone workspace for restructuring an existing resume for a specific job.

## User Inputs

### Job Description

The user pastes the complete JD.

### Existing Resume

The user provides their existing LaTeX source.

```text
JOB DESCRIPTION
┌─────────────────────────────┐
│ Paste JD here               │
└─────────────────────────────┘

RESUME LATEX
┌─────────────────────────────┐
│ Paste / upload .tex source  │
└─────────────────────────────┘
```

## JD Analysis

Extract:

- Role
- Required skills
- Preferred skills
- Experience requirements
- Responsibilities
- Technologies
- Domain concepts
- Education requirements

## LaTeX Resume Analysis

Parse the LaTeX into a structured representation:

```text
Resume
├── Header
├── Education
├── Skills
├── Experience
├── Projects
├── Certifications
└── Achievements
```

## Relevance Analysis

Use the resume-job matching system to determine the relevance of:

- Skills
- Projects
- Experience
- Achievements
- Individual resume content

## Resume Restructuring

The system can:

- Reorder sections
- Reorder projects
- Reorder skills
- Prioritize relevant experience
- Reduce emphasis on unrelated content
- Restructure bullet points
- Improve information density
- Preserve factual information
- Keep the resume ATS-friendly

The system must not invent qualifications, experience, projects, skills, or achievements.

## LaTeX Generation

Generate:

```text
Tailored_Resume.tex
```

Optionally compile:

```text
Tailored_Resume.pdf
```

## Change Explanation

Show the user:

- What was changed
- What was prioritized
- What was de-emphasized
- Which JD requirements were already present
- Which requirements were missing
- What was deliberately not added

Example:

```text
Changes

✓ Moved backend project higher
✓ Prioritized Java and Spring Boot
✓ Reordered technical skills
✓ Reduced emphasis on unrelated project

Not added

✗ Docker
✗ AWS

Reason:
Not present in the supplied resume.
```

---

# 6. Personalized Cold Outreach

## Opportunity-Based Personalization

Use:

```text
User Profile
     +
Company
     +
Job / Opportunity
     ↓
Personalized Email
```

Personalize using:

- Relevant skills
- Relevant projects
- Experience
- Target role
- Company context
- Location
- Opportunity requirements

## Cold-Mail Target Selection

Prioritize companies/opportunities based on:

- Role
- Location
- Salary
- Experience requirements
- Skills
- Industry
- User preferences

## Email Drafting

Generate a personalized cold-mail draft for the user to review and send.

The system assists with preparation rather than automatically sending messages without user control.

---

# 7. Placement Communication Intelligence

This is the placement-specific automation layer.

## Gmail Monitoring

Identify placement-related communications such as:

- Shortlists
- Eligibility lists
- Interview announcements
- Assessments
- Technical rounds
- HR rounds
- Pre-placement talks
- Offers
- Rejections
- Other placement updates

## Attachment Processing

Process placement documents such as:

- Excel files
- PDFs
- Google Sheets
- Word documents
- Scanned/image documents where applicable

## Document Structure Detection

Recognize different column/field names.

Example:

```text
Candidate Name
Student Name
Applicant
        ↓
Candidate

Result
Status
Selection Status
        ↓
Status

Interview Date
Date
Schedule
        ↓
Event Date
```

## Candidate Identification

Determine whether the current user appears in the document.

Possible matching signals:

- Name
- Email
- Student ID / registration identifier
- College
- Department
- Normalized name
- Fuzzy name matching

Produce a confidence score for ambiguous matches.

## Placement Status Classification

Normalize different wording into standard states.

### Shortlisted

- Shortlisted
- Selected for interview
- Eligible for technical round
- Called for interview

→ **SHORTLISTED**

### Rejected

- Rejected
- Not selected
- Not shortlisted

→ **REJECTED**

### Pending

- Under review
- Waitlisted
- Result pending

→ **PENDING**

## Event Information Extraction

Extract:

- Company
- Event type
- Round
- Date
- Start time
- End time
- Venue
- Meeting link
- Reporting time
- Instructions

Possible events:

- Interview
- Coding test
- Assessment
- Pre-placement talk
- Technical round
- HR round

## Duplicate Event Detection

Before creating a calendar event, check whether the same event already exists.

Use event information such as:

- Company
- Event type
- Date
- Time
- Candidate

to identify duplicates.

## Google Calendar Integration

When a relevant event is detected:

```text
Placement Email
      ↓
Document Processing
      ↓
Candidate Identified
      ↓
Shortlisted / Event Detected
      ↓
Event Details Extracted
      ↓
Duplicate Check
      ↓
Google Calendar
```

Example:

```text
Technical Interview
XYZ Technologies
August 22
10:30 AM
Block A
```

## Placement Timeline

Maintain a company-specific progression:

```text
Company
│
├── Application
├── Shortlisted
├── Assessment
├── Technical Interview
├── HR Interview
└── Offer
```

---

# Overall System Flow

```text
                              ┌──────────────────────┐
                              │    USER ONBOARDING   │
                              │                      │
                              │ Profile + Skills     │
                              │ Preferences          │
                              │ Employment constraints│
                              └──────────┬───────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
             JOB INTELLIGENCE     RESUME INTELLIGENCE   CAREER INTELLIGENCE
                    │                    │                    │
                    │                    │                    │
             Job Discovery         Resume Library       Skill Gap Analysis
                    │              Resume Parsing             │
             Job Parsing                  │              Skill Prioritization
                    │              Resume Selection             │
             Hard Filtering               │              Learning Recommendations
                    │                    │                    │
                    └──────────────┬─────┴────────────────────┘
                                   │
                                   ▼
                         NEURAL MATCHING ENGINE
                                   │
                         Resume ↔ Job Similarity
                                   │
                                   ▼
                        PERSONALIZED JOB RANKING
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
              Job Discovery   Resume Choice   Notifications
                    │
                    │
                    ▼
          ┌───────────────────────────────┐
          │ JD-BASED RESUME TAILORING    │
          │                               │
          │ JD + Existing .tex           │
          │          ↓                    │
          │ JD / LaTeX Parsing            │
          │          ↓                    │
          │ Relevance Analysis            │
          │          ↓                    │
          │ Restructuring                 │
          │          ↓                    │
          │ Tailored .tex                 │
          │          ↓                    │
          │ Optional PDF                  │
          └───────────────┬───────────────┘
                          │
                          ▼
                 PERSONALIZED COLD OUTREACH
                          │
                   User Reviews
                          │
                          ▼
                 Manual Email / Application
                          │
                          ▼
                ┌─────────────────────────┐
                │ PLACEMENT COMMUNICATION │
                │       INTELLIGENCE      │
                └────────────┬────────────┘
                             │
                           Gmail
                             │
                 ┌───────────┼───────────┐
                 ▼           ▼           ▼
               Email       Excel        PDF
                 │           │           │
                 └───────────┼───────────┘
                             ▼
                    Candidate Detection
                             │
                             ▼
                     Status Classification
                             │
                             ▼
                    Event Extraction
                             │
                             ▼
                    Duplicate Detection
                             │
                             ▼
                     Google Calendar
                             │
                             ▼
                     Placement Timeline
```

---

# System Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                            │
│                                                                     │
│  Dashboard │ Jobs │ Resumes │ Tailor │ Career │ Outreach │         │
│            │      │         │        │        │ Placement           │
│                                                                     │
│  Minimal, clean, GitHub-inspired visual language                    │
│  without directly copying GitHub's interface                        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                            │
│                                                                     │
│  Profile Management                                                 │
│  Job Intelligence                                                   │
│  Resume Intelligence                                                │
│  Career Intelligence                                                │
│  Resume Tailoring                                                   │
│  Cold Outreach                                                      │
│  Placement Communication                                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
             ┌──────────────────┼───────────────────┐
             ▼                  ▼                   ▼
┌────────────────────┐ ┌────────────────────┐ ┌──────────────────────┐
│   ML / NLP LAYER   │ │ DOCUMENT ENGINE    │ │ AUTOMATION LAYER     │
│                    │ │                    │ │                      │
│ Resume ↔ JD        │ │ Resume parsing     │ │ Gmail monitoring     │
│ semantic matching  │ │ JD parsing         │ │ Attachment handling  │
│ Relevance scoring  │ │ Excel/PDF parsing  │ │ Calendar events      │
│                    │ │ LaTeX parsing      │ │ Duplicate detection  │
│                    │ │ LaTeX generation   │ │                      │
└─────────┬──────────┘ └──────────┬─────────┘ └──────────┬───────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA / STATE LAYER                           │
│                                                                     │
│  User profiles                                                      │
│  Preferences                                                        │
│  Resumes                                                            │
│  Jobs                                                               │
│  Match results                                                      │
│  Tailored resume versions                                           │
│  Outreach history                                                   │
│  Placement events                                                   │
│  Calendar event references                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

# UI / Design Direction

The interface should feel **inspired by GitHub's clarity and developer-oriented aesthetic**, but should not be a visual clone.

### Principles

- Minimal
- Clean
- Spacious
- Information-dense without feeling crowded
- Strong typography
- Subtle borders
- Restrained use of color
- Clear hierarchy
- Compact cards where useful
- Excellent code/editor presentation
- Strong empty states
- Clear status indicators

### Visual language

Think:

```text
GitHub's clarity
       +
Modern developer tool
       +
Clean productivity app
       +
Subtle personal touches
```

Avoid:

- Excessive gradients
- Giant hero sections
- Overly rounded "AI SaaS" cards
- Excessive animations
- Visual clutter
- Copying GitHub's exact navigation, colors, or components

### Key UI areas

```text
┌─────────────────────────────────────────────────────────────┐
│ Logo / App Name                    Search      Profile      │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│ Dashboard    │                                              │
│ Jobs         │                 Main Workspace               │
│ Resumes      │                                              │
│ Tailor       │                                              │
│ Career       │                                              │
│ Outreach     │                                              │
│ Placement    │                                              │
│              │                                              │
│ Settings     │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

The **Resume Tailoring** page should feel especially like a developer workspace, with the JD and LaTeX source presented in clean editor panels and the resulting resume/changes shown alongside them.

---

# Deliberately Out of Scope

The project does **not** automatically submit applications to company websites.

It will not attempt to bypass:

- CAPTCHA
- Login requirements
- MFA
- Bot detection
- Application-site restrictions

The user remains in control of the final application submission and sending of outreach emails.

The project also does **not** attempt to predict whether a specific resume section or achievement will cause someone to be selected. The neural network is focused on **resume ↔ job semantic matching and relevance**, which is a more defensible and achievable ML problem.
