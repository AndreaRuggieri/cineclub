# Cineforum App (Backend API)

Backend API for **cineclubs / cineforums**: private groups of people who watch and discuss films.  
The platform supports **cineclub creation**, **screening series (rassegne)**, **customizable rating criteria**, **controlled voting windows (open/closed per film)**, **join requests**, and **statistics endpoints** designed to power **discussion-friendly charts**.

---

## Table of Contents

- [Key Concepts](#key-concepts)
- [Core Features](#core-features)
- [Actors & Roles](#actors--roles)
- [Permissions Summary](#permissions-summary)
- [Data Model Overview](#data-model-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Run Locally](#run-locally)
- [API Overview](#api-overview)
  - [Auth](#auth)
  - [Cineclubs](#cineclubs)
  - [Invites & Join Requests](#invites--join-requests)
  - [Screening Series (Rassegne)](#screening-series-rassegne)
  - [Films](#films)
  - [Voting](#voting)
  - [Statistics (Charts)](#statistics-charts)
- [Rating Criteria](#rating-criteria)
- [Posters / Media Storage](#posters--media-storage)
- [Notes on Scalability & Next Steps](#notes-on-scalability--next-steps)
- [License](#license)

---

## Key Concepts

- **Cineclub**: a closed group with members and admins. It has a location (Italy / region / province / city) and may allow join requests.
- **Screening Series (Rassegna)**: a collection of films within a cineclub, with:
  - a title and theme (textual “thread” / selection rule)
  - optional dates
  - **custom rating criteria**
  - a set of participants (all, none, or custom)
- **Series Film**: a film instance inside a series with its own **voting status** (open/closed).
- **Votes**: users rate each film using 0–5 stars with **0.5 increments** (Letterboxd-like).

---

## Core Features

✅ Registration & login (JWT)  
✅ App **Superadmin** with credentials `email=a`, `password=a` (seeded at startup)  
✅ Create / browse cineclubs  
✅ Closed groups with:
- invite links (token-based)
- optional join requests (approve/decline)

✅ Create screening series (rassegne) inside a cineclub  
✅ Customizable rating criteria per series  
✅ Add films to a series (title + poster URL/path)  
✅ Open/close voting per film (admin-controlled)  
✅ Votes can be updated while voting is open  
✅ Stats endpoints for charts:
- per film: `min`, `max`, `avg`, `count` per criterion
- per series: same, aggregated for all films

---

## Actors & Roles

### User
- Can register and log in
- Can create cineclubs
- Can join cineclubs via invite or request (if enabled)
- Can request access to series (if member of the cineclub)
- Can vote films **only if**:
  - they are a participant of the series
  - the film voting is open

### Cineclub Admin
- Creator of a cineclub is an admin by default
- Can promote others to admin (future endpoint / or direct DB for now)
- Can create invites
- Can approve/decline cineclub join requests
- Can create series (rassegne)
- Can manage series participants and join requests

### Series Admin
- By default, the cineclub admin who creates the series becomes series admin
- Can approve/decline series join requests
- Can open/close voting per film

### App Superadmin
- Seeded user: `a/a`
- Intended to manage application-level settings (feature flags, moderation, etc.)
- **No extra privileges inside cineclubs** (same permissions as any user in clubs/series)

---

## Permissions Summary

| Action | Who can do it |
|-------|----------------|
| Register/Login | Anyone |
| Create a cineclub | Any authenticated user |
| View cineclub content | Only cineclub members |
| View cineclub public page | Non-members (limited info) |
| Join club via invite | Any authenticated user with invite token |
| Request to join club | Any authenticated user if `join_requests_enabled=true` |
| Approve/decline club join requests | Cineclub admins |
| Create a series (rassegna) | Cineclub admins |
| Request to join series | Cineclub members |
| Approve/decline series join requests | Series admins |
| Add films to series | Series admins |
| Open/close voting for a film | Series admins |
| Vote | Series participants AND film voting open |
| See stats/charts | Cineclub members |

---

## Data Model Overview

Main entities:

- `User`
- `Cineclub`
- `ClubMembership` (user↔club, role)
- `ClubInvite` (token-based invite links)
- `ClubJoinRequest` (PENDING/APPROVED/DECLINED)
- `ScreeningSeries` (rassegna)
- `SeriesParticipant` (user↔series, role)
- `SeriesJoinRequest` (PENDING/APPROVED/DECLINED)
- `Film`
- `SeriesFilm` (film instance in a series, voting open/closed)
- `RatingCriterion` (configurable per series)
- `Vote` (user’s rating per criterion per series film)

DB-level uniqueness constraints prevent:
- duplicate memberships
- duplicate join requests for same user+target
- duplicate film in same series
- duplicate vote for same (user, series film, criterion)

---

## Tech Stack

- **FastAPI** (Python) for HTTP API
- **PostgreSQL** as primary database (recommended)
- **SQLAlchemy 2.0** ORM
- **JWT** authentication (`python-jose`)
- Password hashing with **bcrypt** (`passlib`)

---

## Project Structure
