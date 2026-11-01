# Orion: Multithreaded Neural Semantic PC Search System — College Report Answers

**Team:** Devansh Bhargav (BTCS24O1038) & Divyansh Shekhar Thakur (BTCS24O1044)
**Category:** System Software & Operating Systems | **Session:** July-Dec 2026

> **How to use this file:** Copy the text under each heading and paste it directly into the matching box on your college portal. All tables have been removed and replaced with clean paragraphs and bullet points so they paste cleanly into plain-text or rich-text form boxes. Every section is well under the required word limit.

---

# 1. Project Overview

### 1.1 ABSTRACT
*(Word count: ~210 / 250 words)*

Finding files on a modern Windows PC has become surprisingly slow and frustrating. A typical user drive holds over a million files across system folders, project repositories, and personal directories. Standard Windows Explorer search often takes minutes to scan folders and forces users to remember exact filenames. On the other hand, fast tools like Everything only match raw filenames and lack natural-language filters, media previews, or duplicate detection.

Orion is a lightweight, local-first PC search system built to solve this gap. It uses a three-tier indexing pipeline that reads the NTFS Master File Table (via an embedded Everything engine) and falls back to an 8-thread Python directory crawler when needed. File metadata is stored in an embedded SQLite database running in Write-Ahead Logging (WAL) mode, paired with an FTS5 inverted index that splits paths on underscores, hyphens, and dots.

On top of this index, Orion includes a regex-based natural-language parser. Users can type everyday queries like "pdf from last week larger than 5mb" and get ranked results in under 50 milliseconds. The system also provides an in-app media preview panel, a size-first MD5 duplicate file finder, storage statistics, and a global Ctrl+Space hotkey, all running offline on 127.0.0.1:8472.

---

### 1.2 PROBLEM STATEMENT
*(Word count: ~198 / 250 words)*

Modern laptops and desktops routinely store between 500,000 and 2,000,000 files. Despite fast NVMe SSDs, locating a specific file remains a daily bottleneck for students and developers due to four main problems:

1. Slow Native Search: Windows Search relies on a heavy background indexing service. When searching unindexed folders, it falls back to a sequential directory walk that can take 30 to 120 seconds.
2. Rigid Filename Matching: Users rarely remember whether a file was named daa_lab_4.pdf or DAA-Assignment-4.pdf. Most search utilities fail unless the exact substring is typed, and they cannot understand natural phrases like "videos from last month over 100mb".
3. Fragmented Utility Tools: Checking image resolutions, reading MP3 audio tags, viewing storage breakdown by drive, or finding duplicate files that waste disk space usually requires installing three or four separate third-party programs.
4. Privacy and Resource Overhead: Cloud-connected desktop search tools consume significant RAM and send file metadata over the network.

There is a clear need for a single, self-contained desktop search tool that indexes over a million files in under a minute, answers natural-language queries in milliseconds, and runs 100% offline.

---

### 1.3 OBJECTIVES
*(Word count: ~196 / 250 words)*

The main objectives of the Orion project are:

1. High-Speed Million-File Indexing: Build a multi-tiered background indexer capable of cataloging 1.4+ million files across multiple drives in 30 to 60 seconds using NTFS Master File Table queries and multithreaded os.walk traversal.
2. Sub-50ms Full-Text Search: Design an external-content SQLite FTS5 inverted index with custom token separators (underscores, hyphens, dots, spaces, and brackets) so compound filenames are searchable by individual words without doubling database storage.
3. Natural-Language Query Parsing: Implement a rule-based parser (nlp_parser.py) that extracts file types, extensions, size bounds, relative dates, years, and drive letters directly from plain-English search queries.
4. Multi-Factor Relevance Ranking: Score and sort matched files out of 100 based on token coverage, exact stem matching, folder path hits, file extension match, and modification recency.
5. Built-in Media Preview and Duplicate Detection: Provide instant side-panel previews (JPEG thumbnails, EXIF camera data, MP3/FLAC audio tags, MP4 video dimensions) and a fast two-stage MD5 duplicate scanner.
6. Zero-Config Packaging: Bundle the backend, frontend, and helper tools into a single batch installer that sets up Python, dependencies, and desktop shortcuts automatically.

---

### 1.4 SCOPE & FEASIBILITY
*(Word count: ~212 / 250 words)*

Project Scope:
Orion is designed for Windows 10 and Windows 11 desktops and laptops. The current version covers local and mounted NTFS and FAT32 drives, offering filename and folder search, natural-language constraint filtering, live indexing progress, drive statistics, MD5 duplicate detection, customizable path exclusions, dark and light themes, and system tray integration with a global Ctrl+Space shortcut. To keep the core system fast and dependency-light, Version 1 focuses on lexical and metadata search, while reserving database hooks for neural image and document embeddings in Phase 2.

Feasibility Analysis:
- Technical Feasibility: The system is built using standard Python 3.11+, FastAPI, SQLite3 (built into Python), and Vanilla HTML, CSS, and JavaScript. No paid APIs, external database servers, or dedicated GPUs are required.
- Operational Feasibility: A background daemon checks index freshness every 15 minutes and re-indexes automatically after 4 hours. Normal users can install it with one click via Install Orion.bat.
- Resource and Economic Feasibility: Because SQLite FTS5 uses content='files' external-content tables, indexing 1.43 million files uses only around 350 MB of disk space and under 120 MB of RAM at idle. Everything runs on free, open-source libraries, resulting in zero licensing or hosting cost.

---

# 2. Literature Review & Background

### 2.1 BACKGROUND & SURVEY
*(Word count: ~318 / 400 words)*

Desktop file retrieval sits at the intersection of operating system file systems and information retrieval. On Windows, the New Technology File System (NTFS) stores metadata for every file and directory as records inside a special system file called the Master File Table (MFT). Traditional directory traversal using Win32 FindFirstFile and FindNextFile APIs (or Python's os.walk) visits folders recursively. While portable across all file systems, recursive traversal performs thousands of random disk lookups and struggles when a drive contains over a million small files in deep folders like node_modules or .git. Reading the NTFS MFT directly, as demonstrated by Voidtools Everything, turns a multi-minute tree walk into a sequential read of just a few seconds.

Once file paths are collected, fast querying requires an inverted index rather than SQL LIKE '%term%' table scans. An inverted index breaks each filename and path into normalized word tokens and maps each token to a sorted list of document IDs (posting lists). SQLite's FTS5 (Full-Text Search v5) extension implements this using B-tree segments and ranks results with the Okapi BM25 probabilistic scoring model. However, standard FTS5 tokenizers are designed for prose documents rather than source code or filenames, where words are joined by underscores (final_report_v2.pdf) or dots. Customizing the unicode61 tokenizer's separator characters is essential for file search.

Furthermore, studies on personal information management show that users remember context—such as roughly when they downloaded a file, what type of file it was, or how large it was—much better than they remember exact filenames. Combining an FTS5 inverted index with a lightweight natural-language slot parser allows a desktop search engine to translate human memory cues into structured SQL WHERE clauses without the latency of running a large language model on every keystroke.

---

### 2.2 EXISTING SYSTEMS & LIMITATIONS
*(Word count: ~330 / 400 words)*

We evaluated four widely used desktop search tools before designing Orion:

1. Windows Search (Built-in Explorer Search):
   - How it works: Uses SearchIndexer.exe to index selected user folders (Documents, Desktop) and falls back to slow recursive scanning elsewhere.
   - Limitations: Consumes high disk and CPU in the background, misses developer or secondary drive folders by default, and often takes 30 to 90 seconds when searching across an entire C: or D: drive.

2. Voidtools Everything:
   - How it works: Reads the NTFS MFT directly to list millions of filenames almost instantly.
   - Limitations: Uses a dated Win32 table interface, requires users to know specific syntax (such as ext:pdf size:>5mb dm:lastweek) instead of natural English, does not work on non-NTFS drives without manual configuration, and lacks built-in duplicate scanning, storage analytics, or rich media preview cards.

3. Microsoft PowerToys Run and Wox:
   - How it works: Provides a quick Alt+Space launcher bar that queries Windows Search or plugins.
   - Limitations: Built as an app launcher rather than a full file explorer. It only shows a small dropdown list of 5 to 10 items, has no filter sidebar, cannot preview audio, video, or image metadata, and cannot manage duplicate files.

4. DocFetcher and Recoll:
   - How it works: Java and C++ tools that build full-text indexes of document contents.
   - Limitations: Require heavy upfront indexing, consume large amounts of RAM, frequently crash on corrupted PDFs, and are not designed for fast system-wide filename and media lookup.

Summary of Gaps: Existing tools force a trade-off between raw speed (Everything) and user-friendly filtering or previews. None of them combine MFT-speed indexing, plain-English query parsing, media metadata inspection, and duplicate detection in a clean, modern web UI.

---

### 2.3 COMPARATIVE STUDY & PROPOSED WORK
*(Word count: ~345 / 400 words)*

Comparative Evaluation Against Existing Tools:
- Indexing Speed (1.4M Files): Windows Search takes 15 to 40 minutes; Everything takes 2 to 5 seconds on NTFS only; Orion completes full indexing in 8 to 45 seconds using its 3-tier hybrid engine (Everything HTTP/IPC plus 8-thread os.walk fallback for non-NTFS drives).
- Query Latency: Windows Search takes 2 to 30 seconds on unindexed folders; PowerToys Run takes 100 to 500 ms; Orion returns ranked results in 15 to 48 ms using SQLite FTS5 in WAL mode.
- Natural English Filtering: Neither Everything nor PowerToys Run understands conversational constraints. Orion natively parses phrases like "pdfs from last week larger than 5mb" without requiring special flag syntax.
- Ranking & Folder Discovery: While Everything sorts alphabetically or by raw column, Orion calculates a weighted 100-point relevance score and surfaces matching folders at the top of the view.
- Built-in Media Previews & Duplicate Detection: Unlike Windows Search, Everything, or PowerToys Run, Orion includes an integrated JPEG/EXIF/ID3/MP4 preview drawer and a 4-thread MD5 duplicate scanner in the same interface.

Proposed Work in Orion:
Orion bridges these gaps through four practical engineering choices:
1. Three-Tier Discovery Engine: Orion first queries an embedded Everything.exe HTTP server on port 8481, falls back to es.exe IPC if the port is blocked, and automatically switches to an 8-worker multithreaded os.walk + os.stat pipeline if Everything is unavailable.
2. External-Content FTS5 Index: Instead of duplicating path strings, files_fts points to files(id) via content_rowid and uses custom unicode61 separators so project_final-2025.pdf is searchable by project, final, or 2025.
3. Natural-Language Filter Extraction: Before hitting SQLite, parse_filters() strips out dates, sizes, file types, extensions, and drive letters, turning them into indexed SQL parameters.
4. Two-Pass Duplicate Engine: Instead of hashing all 1.4 million files, Orion first groups files by exact byte size in SQL (HAVING COUNT(*) > 1) and only runs 4-thread MD5 hashing on files that share identical sizes.

---

# 3. Requirements Analysis & Specification

### 3.1 FUNCTIONAL REQUIREMENTS
*(Word count: ~326 / 400 words)*

- FR-1: Automated Multi-Tier File Indexing: The system shall scan all available drive letters (A: through Z:), skip user-defined excluded paths, extract file metadata (path, filename, extension, drive, size, modified, created, file_type), and upsert records into SQLite in batches of 5,000 rows.
- FR-2: Natural-Language and Keyword Search: The system shall parse plain-English queries to extract file categories (image, video, audio, document, code, archive), explicit extensions, size limits (larger or smaller than X KB/MB/GB), time ranges (today, yesterday, last week, this month, or specific years like 2024), and drive letters, then execute an FTS5 MATCH query with an automatic SQL LIKE fallback.
- FR-3: Folder Search and Custom Scoring: When no file-type filter is active, the system shall also match directory names and pin up to 15 matching folders above file results. File results shall be scored from 0 to 100 using token match ratio, exact stem bonus, path match, extension match, and 7-day or 30-day recency bonuses.
- FR-4: Instant Client-Side and Server-Side Filtering: Users shall be able to filter results by file-type tabs in the sidebar (with live badge counts), sort by relevance, size, date, or name, and switch between List and Grid views.
- FR-5: Rich Media Preview and OS Actions: Clicking a result shall open a slide-out panel displaying base64 JPEG thumbnails, image dimensions and EXIF camera info, audio ID3/FLAC tags (artist, album, bitrate, duration), or MP4 video dimensions. Users shall be able to open the file's folder in Windows Explorer (with the file highlighted) or copy its path.
- FR-6: Duplicate File Detection: The system shall identify byte-identical duplicate files using a size-pre-filtered, 4-thread MD5 hashing scan and report wasted disk space per group.
- FR-7: System Tray and Global Hotkey: The app shall run in the Windows system tray and open the search interface from anywhere when Ctrl+Space is pressed.

---

### 3.2 NON-FUNCTIONAL REQUIREMENTS
*(Word count: ~305 / 400 words)*

- NFR-1: Search Response Latency: Keyword and filtered queries over a 1.4-million-file database must return ranked JSON results in under 50 ms for common queries and under 200 ms for multi-token path queries.
- NFR-2: Indexing Throughput and Non-Blocking Concurrency: Full initial indexing should finish within 15 to 45 seconds via the Everything tier (or 3 to 6 minutes via the os.walk fallback). SQLite must use PRAGMA journal_mode=WAL and PRAGMA synchronous=NORMAL so background indexing never blocks live user searches.
- NFR-3: Memory and Storage Footprint: Idle RAM consumption of the Python backend and tray thread must stay below 150 MB. The SQLite database must use an external-content FTS5 virtual table (content='files') to keep total disk usage around 250 to 380 MB per million files.
- NFR-4: 100% Local Privacy and Security: The FastAPI server must bind strictly to loopback (127.0.0.1:8472) so no other machine on the local network can query the user's filesystem. All UI rendering must escape filenames and paths via escHtml() and escJs() to prevent DOM injection from maliciously named files.
- NFR-5: Fault Tolerance and Graceful Degradation: Every subsystem must degrade cleanly: if Everything.exe HTTP fails, fall back to es.exe, then os.walk; if an FTS5 syntax error occurs, fall back to LIKE; if schtasks Explorer launch fails, fall back to ctypes.windll.shell32.SHOpenFolderAndSelectItems and os.startfile.
- NFR-6: Portability: The installer (Install Orion.bat) must use pure ASCII characters so it runs cleanly across any Windows regional codepage without character encoding errors.

---

### 3.3 HARDWARE & SOFTWARE PREREQUISITES
*(Word count: ~282 / 400 words)*

Minimum and Recommended Hardware:
- Processor: Dual-core x86_64 CPU minimum; Intel Core i5 or i7 (11th to 13th Gen) or AMD Ryzen 5 or 7 recommended for 8-thread os.stat and 4-thread MD5 hashing.
- RAM: 4 GB minimum; 8 GB or higher recommended when indexing over 1 million files.
- Storage: Roughly 400 MB of free disk space in %USERPROFILE%\Orion\data\ for the SQLite database (orion.db, .db-wal, .db-shm). An NVMe or SATA SSD is strongly recommended for fast random os.stat reads.
- Display: Any resolution (responsive CSS layout with breakpoint at 900px).

Software Prerequisites:
- Operating System: Windows 10 or Windows 11 (64-bit), using NTFS or FAT32/exFAT drives.
- Python Runtime: Python 3.9 to 3.13 (64-bit) with standard library modules sqlite3 (compiled with FTS5), ctypes, struct, hashlib, concurrent.futures, and threading. Automatically installed via winget or python.org by Install Orion.bat if missing.
- Python Packages (requirements.txt):
  - fastapi and uvicorn[standard] for ASGI web server and REST API routing.
  - Pillow for image metadata, EXIF decoding, and JPEG thumbnail generation.
  - mutagen for MP3, FLAC, OGG, M4A, and WAV audio tag extraction.
  - pystray and keyboard for the Windows system tray icon and global Ctrl+Space listener.
  - python-multipart and aiofiles for FastAPI form and static file support.
- Bundled Native Tools (tools\Everything\): Voidtools Everything.exe (configured for HTTP port 8481) and es.exe CLI IPC client.
- Browser: Any modern browser (Edge, Chrome, Brave, or Firefox).

---

# 4. System Design & Architecture

### 4.1 ARCHITECTURE DESCRIPTION
*(Word count: ~335 / 400 words)*

Orion uses a Local Client-Server Architecture where a single Python process acts as both the background system service and the local web server on http://127.0.0.1:8472. This gives Orion the rich, responsive feel of a modern web app while keeping direct OS-level access to Windows drives, the system tray, and keyboard hooks.

The architecture is organized into four layers:
1. Presentation Layer (frontend/): A single-page application written in vanilla HTML5 (index.html), CSS3 (style.css), and JavaScript (app.js). It manages six views (Search Home, Results, Scan Progress, Statistics, Duplicates, and Settings) without any heavy frontend framework. It communicates with the backend exclusively through asynchronous fetch() calls to /api/* endpoints.
2. API and OS Integration Layer (main.py, tray.py): A FastAPI application served by Uvicorn. On startup, its lifespan manager initializes the SQLite database, launches the background indexer daemon thread, starts the pystray system tray icon and keyboard global Ctrl+Space listener on a daemon thread, and opens the user's browser. It also handles OS shell integration—such as spawning Windows Explorer via an interactive Task Scheduler (schtasks /it) task or Win32 shell32.SHOpenFolderAndSelectItems so the selected file is highlighted on the user's desktop.
3. Core Engine Layer (indexer.py, nlp_parser.py, search.py, duplicates.py, media_meta.py): Independent Python modules that handle file discovery, natural-language query parsing, FTS5 querying and 100-point relevance scoring, two-pass MD5 duplicate detection, and on-demand image, audio, and video header parsing.
4. Storage and Native Helper Layer (config.py, orion.db, tools/Everything/): An embedded SQLite database running in WAL mode with cache_size = -64000 (64 MB RAM cache), paired with an external-content files_fts virtual table and the bundled Everything.exe and es.exe NTFS MFT helpers.

---

### 4.2 SYSTEM MODULES & WORKFLOW
*(Word count: ~348 / 400 words)*

The backend is divided into 8 focused Python modules:

1. config.py: Defines paths, 6 file-type extension sets (covering 95+ extensions), default excluded folders, SQLite connection setup (get_db() with WAL mode and 64 MB cache), and init_db() which creates the tables, indexes, and FTS5 sync triggers.
2. indexer.py: Runs the "orion-indexer" daemon thread. If the index is older than 4 hours, run_index() executes a 4-phase workflow:
   - Phase 1 (Discovery): Queries Everything.exe HTTP JSON API (port 8481), falls back to es.exe IPC, or runs an 8-thread os.walk across all drives.
   - Phase 2 (Metadata): Uses an 8-thread ThreadPoolExecutor to call os.stat() on discovered paths.
   - Phase 3 (Database Upsert): Inserts and updates records in 5,000-row batches (ON CONFLICT(path) DO UPDATE).
   - Phase 4 (Cleanup): Deletes stale rows whose indexed_at timestamp was not updated (DELETE FROM files WHERE indexed_at < ?).
3. nlp_parser.py: parse_filters(query) uses compiled regular expressions to extract file types, extensions, byte size bounds, date windows, years, and drives, returning a structured filter dictionary plus a stripped clean_query.
4. search.py: search() builds parameterized SQL WHERE clauses, runs an FTS5 MATCH query (or LIKE fallback), searches matching folder paths via _search_folders(), scores each file from 0 to 100 in _score_result(), and sorts results in descending order.
5. media_meta.py: Generates base64 JPEG thumbnails and extracts EXIF camera tags via Pillow, audio tags via Mutagen, and MP4 video dimensions by parsing binary tkhd (Track Header) atoms with struct.unpack.
6. duplicates.py: Runs "orion-dupes", finding size-identical files in SQL first, hashing them in 64 KB chunks across 4 threads, and grouping matches by md5_hash.
7. tray.py and main.py: Manage the system tray menu, Ctrl+Space hotkey, and all 17 FastAPI REST routes.

---

### 4.3 DATABASE & DATA FLOW DESIGN
*(Word count: ~330 / 400 words)*

Orion stores all persistent state in a single SQLite file (data/orion.db) containing four standard tables and one virtual FTS5 table:

1. files (Primary Table): Stores id (INTEGER PRIMARY KEY AUTOINCREMENT), path (TEXT UNIQUE), filename, extension, drive, size, modified, created, file_type, md5_hash, ai_description (reserved for Phase 2), and indexed_at. Indexed on extension, file_type, modified, size, drive, and md5_hash.
2. files_fts (FTS5 Virtual Table): Created with USING fts5(path, filename, tokenize = "unicode61 separators '_-. ()[]{}#@!'", content = 'files', content_rowid = 'id'). Because it is an external-content table, it stores only the compact B-tree token lists and fetches actual column values from files via rowid = id. Three SQLite triggers (files_ai, files_ad, files_au) automatically update files_fts whenever a row in files is inserted, deleted, or updated.
3. search_history: Stores recent search strings (query UNIQUE, searched_at) for the autocomplete dropdown.
4. excluded_paths: Stores directories skipped during indexing (C:\Windows, C:\$Recycle.Bin, node_modules, .git, etc.).
5. settings: Key-value store (theme, view_mode, last_indexed).

Data Flow Pipeline:
- Write Flow: Everything.exe or os.walk discovers paths -> 8-thread os.stat() extracts timestamps and byte sizes -> 5,000-row batch INSERT ... ON CONFLICT(path) DO UPDATE writes into files -> files_ai and files_au triggers update files_fts automatically.
- Read Flow: User types query in app.js -> GET /api/search?q=... -> nlp_parser.parse_filters() extracts SQL constraints -> SELECT ... FROM files_fts INNER JOIN files ON fts.rowid = files.id WHERE files_fts MATCH ? -> _score_result() ranks items -> JSON returned to browser and rendered via DocumentFragment.

---

# 5. Technology Stack & Implementation

### 5.1 TECHNOLOGY STACK & TOOLS
*(Word count: ~315 / 400 words)*

Orion's technology stack is purposefully chosen to keep the system fast, self-contained, and free of external server dependencies:

- Backend Runtime (Python 3.11 to 3.13): Powers all file discovery, multithreading, regex parsing, binary header inspection, and database operations.
- Web Framework and Server (FastAPI, Pydantic, and Uvicorn): FastAPI defines the 17 REST API routes and serves the static frontend, Pydantic validates request bodies, and Uvicorn runs the high-speed ASGI HTTP server bound strictly to 127.0.0.1:8472.
- Database Engine (SQLite3 with FTS5 and WAL Mode): Built directly into Python's standard library. Write-Ahead Logging (WAL) allows concurrent background indexing and live searching, while FTS5 provides sub-50ms inverted-index lookups.
- Native File Discovery (Voidtools Everything.exe and es.exe): Reads the Windows NTFS Master File Table over local HTTP (port 8481) or Win32 IPC to list over a million paths in seconds.
- Multithreading and Concurrency (threading and concurrent.futures.ThreadPoolExecutor): Runs background daemon threads for indexing, duplicate scanning, and the system tray, plus an 8-worker pool for os.stat() calls and a 4-worker pool for MD5 file hashing.
- Media Metadata Libraries (Pillow, Mutagen, and Python struct): Pillow decodes image dimensions, EXIF tags, and LANCZOS JPEG thumbnails; Mutagen reads MP3, FLAC, OGG, and M4A audio tags; Python's built-in struct module parses binary MP4/MOV tkhd atoms to read video width and height without needing FFmpeg.
- Desktop and OS Integration (pystray, keyboard, ctypes, and schtasks): Manages the system tray icon, global Ctrl+Space hotkey, and Windows Explorer folder launching.
- Frontend UI (Vanilla HTML5, CSS3, and ES2022 JavaScript): A zero-dependency single-page application supporting dark/light themes, client-side type filtering, and live status polling.
- Packaging and Deployment (Windows Batch and PowerShell): Install Orion.bat automates Python setup, pip installation, archive extraction, and shortcut creation in a 3.2 MB package.

---

### 5.2 IMPLEMENTATION DETAILS & MODULES
*(Word count: ~350 / 400 words)*

Key implementation highlights across our core modules:

1. Custom Relevance Scoring Formula (backend/search.py, _score_result, lines 29–66):
   FTS5 returns up to 400 candidate rows (MAX_RESULTS * 2), which Orion re-ranks using a deterministic 100-point formula combining five signals:
   - Filename Token Match: Adds +40 points if all query tokens appear in the filename; otherwise adds +25 multiplied by (matched tokens / total tokens).
   - Exact Stem Bonus: Adds +25 points if the filename without its extension exactly equals the joined query tokens.
   - Folder Path Match: Adds +15 multiplied by (tokens found in parent directory path / total tokens).
   - Extension Filter Match: Adds +10 points when the file matches an explicit extension filter.
   - Recency Boost: Adds +10 points if the file was modified within the last 7 days, or +5 points if modified within the last 30 days.
   The total is capped at 100. Matching folders discovered by _search_folders() receive a fixed score of 90 so relevant directories appear right at the top of the results.

2. Zero-Dependency MP4 Binary Parser (backend/media_meta.py, get_video_meta, lines 154–196):
   To avoid bundling a 100 MB FFmpeg binary just to read video resolutions, get_video_meta() reads the first 2 MB of an .mp4 or .mov file, locates the ISO Base Media tkhd (Track Header) atom byte signature, and unpacks the 16.16 fixed-point width and height integers using struct.unpack(">I", ...).

3. Sandbox-Safe Explorer Launch (backend/main.py, api_open_folder, lines 167–238):
   When Python runs as a background or elevated process, Windows Job Objects can block explorer.exe from coming to the foreground. Orion solves this with a 3-step fallback: (1) creating a temporary interactive Task Scheduler job (schtasks /create /it) running explorer.exe /select,"<path>", (2) calling Win32 shell32.SHOpenFolderAndSelectItems via ctypes, and (3) falling back to os.startfile().

---

# 6. Testing & Results

### 6.1 TESTING METHODOLOGY & TEST CASES
*(Word count: ~345 / 400 words)*

We tested Orion on a real student laptop (Intel Core i7 13th Gen Mobile, 16 GB RAM, NVMe SSD plus Google Drive mount G:\) holding 1,428,094 indexed files, as well as on a second clean Windows PC to verify the installer.

Our testing methodology covered three levels:
1. Unit Testing: Verified nlp_parser.parse_filters() across 25+ natural-language strings, tested _score_result() boundary cases, and verified escHtml() and escJs() against special characters (single quotes, double quotes, script tags, and ampersands).
2. Fallback and Integration Testing: Intentionally stopped Everything.exe to confirm automatic fallback from Tier 1 (HTTP port 8481) to Tier 2 (es.exe IPC) to Tier 3 (8-thread os.walk).
3. Cross-Machine Installer Testing: Tested Install Orion.bat on a second PC, which caught a real bug where UTF-8 box-drawing characters broke Windows CMD under default codepages; rewriting Install Orion.bat and orion.bat in pure ASCII resolved the issue completely.

Key Test Cases Executed:
- TC-01 (Full Drive Indexing): Started Orion on a PC with 1.42M files across C:\ and G:\. Expected: clean index build into orion.db without crashing. Result: Passed (1,428,094 rows indexed).
- TC-02 (Natural-Language Query Parsing): Searched "pdf from last week larger than 5mb". Expected: parser extracts ext=pdf, size_min=5242880, and a 7-day timestamp filter. Result: Passed (returned matching PDFs in 34 ms).
- TC-03 (Underscore and Dot Tokenizer): Searched "assign 04" to locate DAA_Assign-04.docx. Expected: FTS5 matches split tokens and scores 90+. Result: Passed (ranked #1 in 21 ms).
- TC-04 (Everything Offline Fallback): Terminated Everything.exe and triggered manual re-index. Expected: automatic switch to multithreaded os.walk. Result: Passed (walked 1.32M paths cleanly).
- TC-05 (Duplicate File Scan): Ran MD5 duplicate scan on user directories. Expected: groups byte-identical files and reports wasted MB. Result: Passed.
- TC-06 (Open in Explorer Action): Clicked the Folder button on a result card. Expected: Windows Explorer opens in the foreground with the target file highlighted. Result: Passed.

---

### 6.2 RESULTS & OUTPUTS
*(Word count: ~310 / 400 words)*

Orion successfully indexed 1,428,094 files across C:\ and G:\ drives into data/orion.db without slowing down normal laptop usage.

Key Operational Outputs:
1. Home and Live Search Screen: Opens instantly via http://127.0.0.1:8472 or the global Ctrl+Space shortcut. Typing a query shows autocomplete suggestions from search_history and renders up to 200 ranked file cards plus up to 15 matching folder cards at the top. Each card displays a file-type icon, filename, full directory path, file size badge, modification date, percentage match score (0% to 100%), and quick Folder and Copy Path buttons.
2. Slide-Out Media Preview Panel: Clicking any result opens a non-blocking right-hand drawer. For images, it renders a base64 JPEG thumbnail alongside pixel dimensions, color mode, and EXIF camera model. For audio files (.mp3, .flac), it displays title, artist, album, duration, and bitrate. For .mp4 videos, it shows extracted pixel resolution and file size.
3. Live 4-Stage Scan Progress Page: Displays a real-time progress bar tracking Discovering Files -> Reading Metadata -> Saving to Database -> Done, along with live counters for files found, directories visited, elapsed time, and active indexing engine (Everything vs. Walk).
4. Storage Statistics and Duplicate Finder Pages: The Statistics view shows total indexed files, total disk usage, per-type bar charts, and per-drive breakdowns. The Duplicates page groups byte-identical files with one-click folder access so users can reclaim wasted gigabytes safely.

---

### 6.3 PERFORMANCE ANALYSIS
*(Word count: ~324 / 400 words)*

We benchmarked Orion on a live dataset of 1,428,094 files across two drives (C:\ NVMe SSD and G:\ Google Drive mount):

1. Indexing Speed (3-Tier Comparison):
   - Tier 1 (Everything.exe HTTP API): Collects all file paths in 3 to 6 seconds and completes 8-thread os.stat() plus 5,000-row batch SQLite upserts in roughly 35 to 55 seconds.
   - Tier 3 (os.walk Fallback): When tested without Everything, the 8-thread directory crawler walked both drives and collected 1,322,858 paths in 55 seconds, completing full database insertion in roughly 3.5 minutes—still 5x to 10x faster than Windows Search.

2. Search Query Latency:
   - Single and Multi-Word Filename Queries ("linear algebra", "cat"): 15 ms to 48 ms end-to-end (including NLP regex parsing, FTS5 MATCH, _score_result() ranking, and JSON serialization).
   - Filtered Natural-Language Queries ("pdf larger than 10mb from 2025"): 18 ms to 65 ms, because SQLite applies indexed size and modified bounds alongside the FTS5 inverted index.
   - Folder Search Optimization: Switching folder path lookup from a full-table LIKE scan (which took ~900 ms over 1.4M rows) to an FTS5 prefix query (WHERE files_fts MATCH 'path : "token"*') reduced folder search time by over 90% to under 40 ms.

3. Duplicate Scan Efficiency:
   - By pre-filtering with GROUP BY size HAVING COUNT(*) > 1, Orion skips MD5 hashing on roughly 85% of unique-sized files. Hashing the remaining candidates in 64 KB chunks across 4 threads saturates SSD read bandwidth without freezing the UI.

4. Memory and Disk Overhead:
   - Backend idle RAM usage: roughly 85 to 115 MB.
   - Database size for 1.42M files: roughly 340 MB (thanks to the content='files' external-content FTS5 design).

---

# 7. Conclusion & Future Scope

### 7.1 KEY ACHIEVEMENTS
*(Word count: ~195 / 250 words)*

- Million-File Scale on Consumer Hardware: Successfully indexed and searched 1,428,094 files on a standard laptop with sub-50ms average query latency.
- Resilient 3-Tier Indexing Architecture: Combined the raw NTFS MFT speed of Everything.exe HTTP and es.exe IPC with a zero-dependency, 8-thread Python os.walk + os.stat fallback so the system works reliably on any Windows PC.
- Plain-English Search Bar: Built a fast regex NLP parser (nlp_parser.py) that lets users filter by file category, extension, size, date window, year, and drive without learning complex search flags.
- Smart Storage and Duplicate Tools: Delivered an integrated size-first, 4-thread MD5 duplicate detector, drive analytics dashboard, and a dependency-light media preview panel (using Pillow, Mutagen, and binary MP4 tkhd atom parsing).
- One-Click Portable Installer: Created a pure-ASCII Windows batch installer (Install Orion.bat) and packaging pipeline (package_build.py) that sets up Python, pip packages, and desktop shortcuts automatically on a clean PC.

---

### 7.2 LIMITATIONS & CHALLENGES
*(Word count: ~204 / 250 words)*

1. Lexical vs. Content Search in Version 1: The core v1 engine indexes filenames, folder paths, and file metadata. If a photo is named IMG_20260704.jpg or a textbook PDF is named dhgfdshg.pdf, a filename search for "sunset" or "linear algebra" cannot see inside the file unless neural content indexing (Phase 2) is enabled.
2. Polling vs. Real-Time File Watcher: The background indexer checks for stale data every 15 minutes (re-indexing after 4 hours) or when triggered manually, rather than subscribing to live NTFS USN Journal events on every file creation.
3. Cloud Placeholder Files: Online-only files inside OneDrive or Google Drive folders report their size in os.stat(), but reading their contents for MD5 duplicate hashing requires Windows to download them first.
4. Windows Process Sandbox and Codepage Quirks: Launching explorer.exe /select from a background Python service required a 3-stage fallback (schtasks /it -> Win32 SHOpenFolderAndSelectItems -> os.startfile), and Unicode characters in .bat files had to be replaced with pure ASCII for cross-PC compatibility.

---

### 7.3 FUTURE SCOPE
*(Word count: ~218 / 250 words)*

We have designed—and already prototyped in our Phase 2 branch—a Multimodal Neural Semantic Search Engine that plugs directly into Orion's reserved database hooks (ai_description, ai_items, ai_vectors, and content_fts):

1. Visual Image and Video Search (OpenAI CLIP): Using CLIP ViT-L/14 (768-dim FP16 embeddings on CUDA, with automatic ViT-B/32 CPU fallback), Orion encodes photos and 5 sampled frames per video into GPU memory and auto-tags them across a 303-concept taxonomy (such as cat -> animal, pet, sunset, or invoice). Users can search "sunset" or "football match" and find files with random camera filenames (20260704_184619.jpg).
2. Deep Document and Code Understanding (BAAI/bge-small-en-v1.5): A crash-isolated 5-process PDF helper pool (pdf_helper.py using PyMuPDF) extracts titles, tables of contents, and sampled pages from 600-page PDFs, Word, PowerPoint, Excel, and code files, indexing both exact text (content_fts) and 384-dim semantic meaning vectors—and even running 60-DPI cover renders through CLIP for scanned handwritten notes.
3. Hybrid 4-Signal Z-Score Ranking and "Find Similar": Combines filename match, BM25 content match, BGE meaning similarity, and CLIP visual z-scores into a single unified score, plus one-click "Find Similar Files" k-NN lookup.

---

### 7.4 CONCLUSION
*(Word count: ~158 / 200 words)*

Orion set out to fix a daily frustration faced by every student and developer: finding files quickly across cluttered, million-file Windows drives without giving up natural filtering or local privacy. By combining a three-tier NTFS and multithreaded discovery pipeline, an external-content SQLite FTS5 inverted index in WAL mode, a natural-language filter parser, and a clean vanilla JS interface with built-in media previews and MD5 duplicate detection, Orion delivers sub-50ms search speeds with a tiny 3.2 MB installer footprint. Testing on a real 1.42-million-file system confirmed that careful systems engineering—such as batching SQLite transactions, pre-filtering duplicates by byte size, and tuning FTS5 token separators—can outperform built-in OS tools by an order of magnitude while laying a clean foundation for multimodal AI search.

---

# 8. References

### 8.1 CITATIONS & BIBLIOGRAPHY
*(Word count: ~285 / 400 words)*

1. Hipp, D. R., Kennedy, D., & Mistachkin, J. (2020). SQLite FTS5 Extension Documentation & Write-Ahead Logging (WAL) Architecture. SQLite Consortium. https://www.sqlite.org/fts5.html
2. Carpenter, D. (2023). Everything Search Engine: NTFS Master File Table Indexing and HTTP/IPC SDK Reference. Voidtools. https://www.voidtools.com/support/everything/sdk/
3. Robertson, S., & Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval, 3(4), 333–389.
4. Ramirez, S. (2024). FastAPI: High-Performance Asynchronous Web Framework for Python based on Starlette and Pydantic. https://fastapi.tiangolo.com/
5. Clark, A., et al. (2024). Pillow (PIL Fork) Imaging Library Documentation. Python Software Foundation. https://pillow.readthedocs.io/
6. Reiter, C., et al. (2023). Mutagen: Python Multimedia Metadata Tagging Library. Quod Libet Development Team. https://mutagen.readthedocs.io/
7. ISO/IEC 14496-12 (2022). Information Technology — Coding of Audio-Visual Objects — Part 12: ISO Base Media File Format (tkhd Track Header Box Specification).
8. Radford, A., Kim, J. W., Hallacy, C., et al. (2021). Learning Transferable Visual Models From Natural Language Supervision (CLIP). Proceedings of the 38th International Conference on Machine Learning (ICML), PMLR 139:8748–8763.
9. Xiao, S., Liu, Z., Zhang, P., & Muennighoff, N. (2023). C-Pack: Packaged Resources To Advance General Chinese Embedding (BAAI BGE Text Embeddings). arXiv preprint arXiv:2309.07597.
10. Russinovich, M. E., Solomon, D. A., & Ionescu, A. (2017). Windows Internals, Part 1: System Architecture, Processes, Threads, Memory Management, and NTFS (7th ed.). Microsoft Press.

---

# 9. Annexure & Image Upload Guide

### Suggested 5 Images & Captions (Max 5 images, < 512 KB each)
- Image 1 (Upload in Section 4.1 Architecture Description):
  Caption: Figure 1: Orion Four-Layer Local Client-Server Architecture and 3-Tier Indexing Pipeline.
- Image 2 (Upload in Section 4.3 Database & Data Flow Design):
  Caption: Figure 2: SQLite WAL Database Schema with External-Content FTS5 Virtual Table and Sync Triggers.
- Image 3 (Upload in Section 6.2 Results & Outputs):
  Caption: Figure 3: Orion Search Interface showing ranked file and folder results and the slide-out Media Preview Panel.
- Image 4 (Upload in Section 6.3 Performance Analysis):
  Caption: Figure 4: Live 4-Stage Indexing Progress and Storage Analytics across 1.42 million indexed files.
- Image 5 (Upload in Section 7.3 Future Scope — use ui_ai_brain.png or ui_search_sunset.png):
  Caption: Figure 5: Phase 2 Prototype — Multimodal CLIP + BGE-small Neural Semantic Search and AI Brain Dashboard.

### 9.1 PROJECT ARTIFACTS & URLS (Titles to paste into the 5 slots)
- Artifact #1 Title: GitHub Repository — Orion Source Code (Backend, Frontend & Installer)
- Artifact #2 Title: Standalone Windows Installer Package (Install Orion.bat + orion.zip)
- Artifact #3 Title: Live Demonstration & Million-File Search Walkthrough Video
- Artifact #4 Title: Complete 5-Volume Technical Documentation & Code Deep-Dive Series
- Artifact #5 Title: Phase 2 Neural Semantic Search Prototype & Architecture Blueprint (CLIP + BGE)
