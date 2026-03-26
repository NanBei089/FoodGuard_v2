# Food Label Analyzer

Backend scaffold for the `food-label-analyzer` service, aligned to `提示词/01.md` and prepared for the follow-up implementation documents in `提示词/02.md` through `提示词/07.md`.

## Current Status

Implemented now:
- project structure, dependency manifests, and configuration contract
- shared core modules for logging, error handling, security, database, and Redis helpers
- FastAPI application bootstrap, dependency wiring, router aggregation, and health endpoint
- Alembic bootstrap aligned to the project metadata entrypoint
- normalized placeholder modules for services, workers, tasks, schemas, and future ORM models

Still intentionally placeholder-only:
- auth, analysis, and report business workflows
- full ORM model set beyond the currently mapped `User` model
- Celery task orchestration and report persistence
- OCR runtime server-side implementation
- SMTP delivery, object storage workflows, and report query logic

## Structure Map

- `app/core/`: settings, security, errors, logging, and low-level email transport boundaries
- `app/db/`: async and sync database session factories plus Redis helpers
- `app/models/`: ORM model entrypoints and forward-looking enum/model placeholders for DOC-02
- `app/schemas/`: request and response schema placeholders for DOC-03, DOC-04, and DOC-06
- `app/api/v1/`: thin router modules that stay reserved for HTTP orchestration only
- `app/services/`: business orchestration boundaries
- `app/tasks/`: Celery app and task entrypoints
- `app/workers/`: AI and external capability adapters

## Roadmap by Prompt Document

- `提示词/01.md`: infrastructure and project skeleton
- `提示词/02.md`: ORM models, enums, JSONB contracts, and Alembic migrations
- `提示词/03.md`: auth flows, email delivery, and related schemas/services/routes
- `提示词/04.md`: upload flow, storage, task scheduling, and report entrypoints
- `提示词/05.md`: YOLO, OCR, extractor, RAG, LLM, and prompt-chain implementation
- `提示词/06.md`: report persistence, query, and serialization rules
- `提示词/07.md`: API-level response, error, and documentation polish

## Notes

- The default `YOLO_MODEL_PATH` now points to the checked-in `./models_store/yolo/yolo26s.onnx`.
- OCR runtime is configured with separate `PADDLEOCR_OCR_ENDPOINT` and `PADDLEOCR_TABLE_ENDPOINT` values.
- Placeholder modules now fail explicitly with `NotImplementedError` where a later document expects a callable implementation.

## Documentation

- Backend overview: [docs/backend.md](file:///e:/GraduationProject/foodguard/food-label-analyzer/docs/backend.md)
- Frontend API guide: [docs/api.md](file:///e:/GraduationProject/foodguard/food-label-analyzer/docs/api.md)
