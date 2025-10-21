from __future__ import annotations

from typing import Any, Dict, List, Optional

import strawberry
from strawberry.fastapi import GraphQLRouter


# ----------------------------- GraphQL types -------------------------------- #

@strawberry.type
class Health:
    ok: bool
    service: str


@strawberry.type
class AIChatPayload:
    ok: bool
    model: str
    message: str


@strawberry.input
class ChatMessageInput:
    role: str
    content: str


@strawberry.input
class AIChatInput:
    model: Optional[str] = None
    messages: List[ChatMessageInput] = strawberry.field(default_factory=list)
    stream: Optional[bool] = False


@strawberry.type
class ExtractPayload:
    ok: bool
    model: str
    data: Optional[strawberry.scalars.JSON]
    raw: Optional[str]
    used_ocr: bool
    ocr_note: Optional[str]
    image_size: Optional[strawberry.scalars.JSON]
    page_count: Optional[int]
    prompt: Optional[strawberry.scalars.JSON]


@strawberry.input
class FileRefInput:
    kod: int
    fileId: int
    fileHash: str


@strawberry.input
class ExtractInput:
    ref: FileRefInput
    prompt: Optional[str] = None
    model: Optional[str] = None
    run_ocr: Optional[bool] = True
    return_prompt: Optional[bool] = False


# ----------------------------- Resolvers ------------------------------------ #

@strawberry.type
class Query:
    @strawberry.field
    def status(self) -> Health:
        return Health(ok=True, service="gateway")

    @strawberry.field
    def llm_models(self) -> strawberry.scalars.JSON:
        # Import lazily to avoid circulars
        from apps.gateway.pipeline_router import list_models  # type: ignore
        return list_models()


@strawberry.type
class Mutation:
    @strawberry.mutation
    def ai_chat(self, input: AIChatInput) -> AIChatPayload:
        from apps.gateway.pipeline_router import ChatIn, ChatMessage, chat  # type: ignore

        body = ChatIn(
            model=input.model,
            messages=[ChatMessage(role=m.role, content=m.content) for m in input.messages],
            stream=bool(input.stream),
        )
        out = chat(body)  # calls the REST handler function directly
        return AIChatPayload(ok=out["ok"], model=out["model"], message=out["message"])

    @strawberry.mutation
    def ai_extract(self, input: ExtractInput) -> ExtractPayload:
        from apps.gateway.pipeline_router import ExtractIn, FileRef, vision_extract  # type: ignore

        body = ExtractIn(
            ref=FileRef(kod=input.ref.kod, fileId=input.ref.fileId, fileHash=input.ref.fileHash),
            prompt=input.prompt,
            model=input.model,
            run_ocr=bool(input.run_ocr),
            return_prompt=bool(input.return_prompt),
        )
        out = vision_extract(body)  # uses FastAPI deps defaults internally

        return ExtractPayload(
            ok=out["ok"],
            model=out["model"],
            data=out.get("data"),
            raw=out.get("raw"),
            used_ocr=out.get("used_ocr", False),
            ocr_note=out.get("ocr_note"),
            image_size=out.get("image_size"),
            page_count=out.get("page_count"),
            prompt=out.get("prompt"),
        )


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema)
