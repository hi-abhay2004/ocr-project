# Handwritten Evaluation Test Pack

Use this file to generate one image per test case in Gemini, then upload each image separately through the application.

## Important Gemini Instructions

Use the following requirements at the beginning of every image prompt:

```text
Generate a realistic photograph or scan of a single handwritten university exam answer-sheet page. The writing must look genuinely written by a human student with a black or dark-blue ballpoint pen. Do not use typed text, computer fonts, digital overlays, printed labels, decorative handwriting, or a clean presentation-style layout. Keep natural variation in letter size, baseline, spacing, pressure, and alignment. Use white or slightly off-white paper. The page should look like a real student answer sheet photographed from above with mild shadows and natural imperfections. Do not add explanations outside the paper. Output only the answer-sheet image.
```

For the cleanest tests, generate each case as a separate image. Do not combine multiple cases into one image.

## Test 1: Normal Handwritten Answer

### Question

```text
Define BCNF and explain how it differs from 3NF.
```

### Model Answer

```text
A relation is in Boyce-Codd Normal Form when, for every non-trivial functional dependency X determines Y, X is a superkey. BCNF is stricter than Third Normal Form because 3NF may allow a determinant that is not a superkey when the dependent attribute is prime, while BCNF does not. BCNF reduces redundancy and update anomalies.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a single handwritten university exam answer-sheet page. The writing must look genuinely written by a human student with a black or dark-blue ballpoint pen. Do not use typed text, computer fonts, digital overlays, printed labels, decorative handwriting, or a clean presentation-style layout. Keep natural variation in letter size, baseline, spacing, pressure, and alignment. Use white or slightly off-white paper. The page should look like a real student answer sheet photographed from above with mild shadows and natural imperfections. Do not add explanations outside the paper. Output only the answer-sheet image.

Write this answer by hand:

1) BCNF is a normal form for relational database schemas.
2) A relation is in BCNF when for every non-trivial functional dependency X determines Y, X is a superkey.
3) BCNF is stricter than 3NF and helps reduce redundancy and update anomalies.

Write the question number clearly as 1) at the beginning. Use two or three handwritten paragraphs. Do not draw diagrams, arrows, tables, underlines, or strike-throughs.
```

Expected: one `TEXT` block, readable reconstructed text, concepts mostly covered, no special annotations.

## Test 2: Blank Page

### Question

```text
Explain database normalization.
```

### Model Answer

```text
Database normalization organizes relational data to reduce redundancy and update anomalies. First Normal Form requires atomic values, Second Normal Form removes partial dependency on a composite key, and Third Normal Form removes transitive dependency.
```

### Gemini Image Prompt

```text
Generate a realistic photograph of one completely blank university answer-sheet page. Use slightly off-white paper with mild camera shadow and very small natural paper texture. Do not include handwriting, printed text, question numbers, lines, diagrams, marks, logos, or borders. Output only the blank page image.
```

Expected: no answer blocks or an empty/low-confidence evaluation; all concepts missing; zero or near-zero marks; no crash.

## Test 3: Multiple Questions on One Page

### Questions

```text
1. Define BCNF.
2. What is a deadlock?
3. Explain indexing in databases.
```

### Model Answer

```text
1. BCNF requires every determinant in every non-trivial functional dependency to be a superkey.
2. A deadlock occurs when processes wait indefinitely for resources held by one another.
3. An index is an auxiliary data structure that speeds up record retrieval at the cost of storage and update overhead.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a single handwritten university exam answer-sheet page. The writing must look genuinely written by a human student with a black ballpoint pen. Use natural handwriting imperfections and mild camera perspective. Write exactly three clearly separated answer blocks:

1) BCNF requires every determinant in every non-trivial functional dependency to be a superkey.

2) A deadlock occurs when processes wait indefinitely for resources held by one another.

3) An index is an auxiliary data structure that speeds up record retrieval at the cost of storage and update overhead.

Write the numbers 1), 2), and 3) by hand at the start of the corresponding blocks. Leave visible vertical spacing between blocks. Do not underline, strike through, draw arrows, or add diagrams. Output only the answer-sheet image.
```

Expected: three blocks assigned to questions 1, 2, and 3 with separate evaluations.

## Test 4: Multi-Page Continuation

Generate two separate images for this case and upload them together in page order.

### Question

```text
Explain deadlock prevention and recovery.
```

### Model Answer

```text
Deadlock prevention ensures that at least one necessary deadlock condition never occurs. Wait-die and wound-wait are timestamp-based schemes. Deadlock recovery detects cycles in a wait-for graph and then aborts or rolls back selected processes to release resources.
```

### Page 1 Gemini Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page. Use genuine student handwriting in dark-blue pen, mild shadows, slight skew, and natural uneven spacing. At the top write by hand:

1) Deadlock prevention ensures that at least one necessary deadlock condition never occurs. Wait-die and wound-wait are timestamp-based schemes.

The answer must visibly continue beyond the bottom of the page. Do not write a conclusion. Do not add another question number, diagrams, tables, underlines, arrows, or strike-throughs. Output only the page image.
```

### Page 2 Gemini Prompt

```text
Generate a realistic photograph or scan of the continuation page of a handwritten university answer-sheet answer. Use the same dark-blue student handwriting style as the previous page. Start directly with:

Deadlock recovery detects cycles in a wait-for graph and then aborts or rolls back selected processes to release resources.

Do not write a question number because this is a continuation page. Do not add any new question. Output only the page image.
```

Expected: page 2 remains associated with question 1 and its text is combined with page 1.

## Test 5: Unnumbered Single-Question Answer

### Question

```text
What is a primary key?
```

### Model Answer

```text
A primary key is an attribute or set of attributes that uniquely identifies each row in a relation. It cannot contain duplicate values or NULL values.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a single handwritten university answer-sheet page. Use natural black-pen handwriting with mild unevenness and camera shadow. Write only this answer, with no question number anywhere on the page:

A primary key is an attribute or set of attributes that uniquely identifies each row in a relation. It cannot contain duplicate values or NULL values.

Do not add a heading, number, diagram, table, underline, arrow, or strike-through. Output only the answer-sheet image.
```

Expected: because the exam has one question, the system assigns the unlabeled block to that question.

## Test 6: Crossed-Out Text and Correction

### Question

```text
Explain the purpose of indexing.
```

### Model Answer

```text
An index is a data structure that speeds up searches by allowing the database to locate rows without scanning the entire table. Indexes improve read performance but require additional storage and may slow inserts and updates.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a single handwritten university exam answer page. Use genuine student handwriting with a dark-blue ballpoint pen and mild natural camera imperfections. Write:

1) An index is a data structure that speeds up searches by allowing the database to locate rows without scanning the entire table. Indexes improve read performance.

Then write the phrase "Indexes always make every operation faster" on a separate line and cross it out heavily with one or two visible handwritten strokes. After the crossed-out phrase, write the correction:

They require additional storage and may slow inserts and updates.

Make the crossed-out phrase clearly different from the final correction. Do not cross out the correction. Output only the answer-sheet image.
```

Expected: a `STRIKE` annotation with correction intent; the crossed-out sentence should not be treated as final answer text.

## Test 7: Underlined Concept

### Question

```text
What is a foreign key and why is it useful?
```

### Model Answer

```text
A foreign key is an attribute that references a candidate key in another relation. It enforces referential integrity and prevents records from referring to nonexistent rows.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page using a dark-blue pen. Write:

1) A foreign key is an attribute that references a candidate key in another relation. It enforces referential integrity and prevents records from referring to nonexistent rows.

Draw a single natural handwritten underline directly beneath the words "referential integrity" only. Do not underline other words. Do not strike through anything and do not draw arrows or diagrams. Output only the answer-sheet image.
```

Expected: an `UNDERLINE` annotation with `EMPHASIS` intent around the intended words.

## Test 8: Margin Note and Arrow

### Question

```text
Explain two-phase locking.
```

### Model Answer

```text
Two-phase locking has a growing phase in which a transaction obtains locks and a shrinking phase in which it releases locks. It guarantees conflict serializability. A transaction cannot obtain a new lock after it releases its first lock.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page. Use dark-blue human handwriting and natural paper/camera imperfections. In the main answer column write:

1) Two-phase locking has a growing phase in which a transaction obtains locks and a shrinking phase in which it releases locks.

In the right margin, write this handwritten note:

It guarantees conflict serializability.

Draw a clear handwritten arrow from the margin note toward the main answer sentence. Continue the main answer below with:

A transaction cannot obtain a new lock after it releases its first lock.

Do not use typed text. Do not add a table or diagram. Output only the page image.
```

Expected: `MARGIN` and `ARROW` annotations; margin text should be included near the relevant answer position.

## Test 9: Diagram

### Question

```text
Draw and explain the basic client-server architecture.
```

### Model Answer

```text
In a client-server architecture, clients send requests to a server. The server processes the requests, accesses data or services, and sends responses back to the clients.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page. Use dark-blue human handwriting. At the top write:

1) Client-server architecture:

Below it, draw a hand-drawn diagram with two boxes labelled Client and Server. Draw arrows labelled request from Client to Server and response from Server to Client. Under the diagram write:

Clients send requests to a server. The server processes requests, accesses data or services, and sends responses back to clients.

Make the boxes and arrows look hand-drawn, not digitally perfect. Do not add typed labels or computer graphics. Output only the answer-sheet image.
```

Expected: the VLM identifies `DIAGRAM` and describes the boxes, labels, and connections; the description is sent to grading.

## Test 10: Handwritten Table

### Question

```text
Compare clustered and non-clustered indexes.
```

### Model Answer

```text
A clustered index determines the physical order of rows and usually allows only one per table. A non-clustered index is a separate structure containing keys and pointers to rows, so a table can have multiple non-clustered indexes.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page using a dark pen. Write:

1) Compare clustered and non-clustered indexes.

Then draw a hand-drawn two-column table. The handwritten column headings must be Clustered Index and Non-Clustered Index. In the first column write: physical row order, usually one per table. In the second column write: separate keys and pointers, multiple indexes possible.

Make the table lines uneven and hand-drawn. Do not create a computer-generated grid or typed text. Output only the answer-sheet image.
```

Expected: `TABLE` content type and a VLM transcription preserving the two-column information.

## Test 11: Mathematical Equation

### Question

```text
Write the formula for precision and recall.
```

### Model Answer

```text
Precision equals true positives divided by true positives plus false positives. Recall equals true positives divided by true positives plus false negatives.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page. Use human handwriting with a dark-blue pen. Write:

1) Precision and recall formulas:

Precision = TP / (TP + FP)
Recall = TP / (TP + FN)

Under the equations, write: Precision measures how many predicted positives are correct. Recall measures how many actual positives are found.

Make the equations handwritten, with natural variation and no typed fonts. Do not add a digital math layout. Output only the answer-sheet image.
```

Expected: `EQUATION` content type and VLM transcription into plain-text math.

## Test 12: Poor-Quality Photograph

### Question

```text
Explain ACID properties of a transaction.
```

### Model Answer

```text
Atomicity means a transaction is completed entirely or not at all. Consistency preserves database rules. Isolation keeps concurrent transactions from interfering incorrectly. Durability ensures committed changes survive failures.
```

### Gemini Image Prompt

```text
Generate a realistic low-quality photograph of a handwritten university answer-sheet page taken quickly with a phone. Use genuine dark-blue handwriting, mild motion blur, uneven lighting, a soft shadow across one corner, slight perspective skew, and moderate compression artifacts. The writing must remain partially legible but visibly difficult to read. Write:

1) Atomicity means a transaction is completed entirely or not at all. Consistency preserves database rules. Isolation keeps concurrent transactions from interfering incorrectly. Durability ensures committed changes survive failures.

Do not add diagrams, tables, underlines, arrows, or strike-throughs. Output only the poor-quality answer-sheet image.
```

Expected: VLM extraction with lower confidence; teacher review should be required rather than silently trusting the result.

## Test 13: Mixed Annotation Page

### Question

```text
Explain the difference between a process and a thread.
```

### Model Answer

```text
A process is an independent program with its own address space. A thread is a smaller execution unit within a process and shares the process address space with other threads. Threads are usually cheaper to create and switch between.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page using dark-blue human handwriting. Write:

1) A process is an independent program with its own address space. A thread is a smaller execution unit within a process and shares the process address space with other threads. Threads are usually cheaper to create and switch between.

Cross out the words "independent program" in the first sentence and write "running program" above them as a correction. Underline the words "shares the process address space". In the right margin write "important distinction" and draw an arrow from that note toward the sentence about threads.

Make every annotation visibly handwritten and imperfect. Do not add diagrams or tables. Output only the answer-sheet image.
```

Expected: multiple annotation kinds in one block: strike, underline, margin, and arrow.

## Test 14: Corrupt File / Invalid Image

This case cannot be generated as a visually handwritten image. Create it manually as a file named `corrupt-answer.png` containing random bytes or rename a text file to `.png`.

### Question

```text
What is a database transaction?
```

### Model Answer

```text
A database transaction is a sequence of operations treated as one logical unit of work. It should preserve atomicity, consistency, isolation, and durability.
```

### Expected

- Upload may be accepted if only the declared MIME type is checked.
- Worker should eventually mark the sheet `FAILED`.
- The UI should show a readable decode error.
- Retry should not silently show an old result.

## Test 15: Wrong Question Number in a Multi-Question Exam

### Questions

```text
1. Define a primary key.
2. Define a foreign key.
```

### Model Answer

```text
1. A primary key uniquely identifies each row and cannot be NULL.
2. A foreign key references a key in another table and enforces referential integrity.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of a handwritten university answer-sheet page with dark-blue human handwriting. At the beginning write the label 3) even though the answer text is:

A primary key uniquely identifies each row in a relation and cannot contain NULL values.

Do not write labels 1) or 2). Do not add diagrams, tables, annotations, or other answers. Output only the answer-sheet image.
```

Expected: in a multi-question exam, the system should not confidently assign this content to question 1 or 2 without a safe matching strategy. It should produce an empty/low-confidence result or make the mismatch visible for review.

## Test 16: Very Long Answer

### Question

```text
Explain database management systems in detail.
```

### Model Answer

```text
A database management system provides a structured way to store, retrieve, update, and protect data. It supports data definition, data manipulation, transaction management, concurrency control, recovery, security, indexing, and query optimization. A DBMS reduces redundancy and provides controlled access to shared data.
```

### Gemini Image Prompt

```text
Generate a realistic photograph or scan of three consecutive handwritten university answer-sheet pages. Use the same human student's dark-blue handwriting throughout. On page 1 write the question number 1) and begin a detailed answer about database management systems. Continue naturally onto page 2 and page 3 without repeating the question number. Fill most of each page with realistic handwritten paragraphs, leaving normal margins and occasional line-spacing variation. Do not add diagrams, tables, strike-throughs, underlines, or arrows. Output the three pages as separate page images in reading order.
```

Expected: pages are processed without truncation, answer text is combined, and the provider does not exceed its image/context limits.

## Test Procedure for Every Image

For each generated case:

1. Create a new exam so old concepts/results do not interfere.
2. Add the question and exact model answer from this file.
3. Wait until concepts appear in the question editor.
4. Enroll one student.
5. Upload only the image(s) for that case.
6. Watch the pipeline status until `DONE` or `FAILED`.
7. Open the teacher review page.
8. Record:
   - extracted question number
   - number of blocks
   - reconstructed text
   - content type
   - annotations and bounding boxes
   - VLM confidence
   - concept status
   - marks
   - feedback
9. Compare the output with the expected result above.
10. Approve only after checking the overlay and concept evidence.
11. Log in as the student and confirm only approved, student-safe data is visible.

## Recommended Result Log

```text
Case:
Image filename:
Exam/question:
Upload status:
Final sheet status:
Detected blocks:
Detected question number:
Content type:
Annotations:
Reconstructed text correct: YES / NO
Concept statuses:
Automatic marks:
Confidence:
Teacher override:
Student result visible after approval: YES / NO
Notes:
```

## Important Interpretation Rule

These images test the software workflow and VLM extraction behavior. They do not establish grading accuracy against real student handwriting. For a meaningful accuracy study, repeat the same cases with real teacher-created handwritten pages and record the teacher's expected block boundaries, transcription, annotations, concept statuses, and marks.
