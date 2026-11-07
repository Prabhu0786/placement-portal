
import logging
import os
import time

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from google import genai
from google.genai import types


logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_ITEMS = 10

RETRYABLE_STATUS_CODES = {429, 500, 503, 504}
MAX_ATTEMPTS_PER_MODEL = 2


def generate_ai_response(client, primary_model, prompt):

    # Primary model remains Gemini 3.8.
    # Fallback is used only if the primary model fails.
    fallback_model = os.getenv(
        "GEMINI_FALLBACK_MODEL",
        "gemini-2.5-flash-lite"
    )

    models_to_try = [primary_model]

    if fallback_model and fallback_model != primary_model:
        models_to_try.append(fallback_model)

    last_error = None

    for model_name in models_to_try:

        for attempt in range(MAX_ATTEMPTS_PER_MODEL):

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )

                answer = (response.text or "").strip()

                if answer:
                    if model_name != primary_model:
                        logger.info(
                            "Fallback Gemini model used: %s",
                            model_name
                        )

                    return answer

                last_error = RuntimeError(
                    "Gemini returned an empty response."
                )
                break

            except Exception as exc:

                last_error = exc

                status_code = getattr(
                    exc,
                    "status_code",
                    None
                )

                if status_code not in RETRYABLE_STATUS_CODES:
                    logger.exception(
                        "Gemini model %s failed.",
                        model_name
                    )
                    break

                logger.warning(
                    "Gemini model %s returned status %s. "
                    "Attempt %s of %s.",
                    model_name,
                    status_code,
                    attempt + 1,
                    MAX_ATTEMPTS_PER_MODEL
                )

                if attempt + 1 < MAX_ATTEMPTS_PER_MODEL:
                    time.sleep(1.5 * (attempt + 1))

    if last_error:
        raise last_error

    raise RuntimeError("No Gemini model was available.")


@login_required
def chat(request):

    history = request.session.get(
        "ai_chat_history",
        []
    )

    if request.method == "POST":

        message = request.POST.get(
            "message",
            ""
        ).strip()

        if not message:
            return render(
                request,
                "ai_assistant/chat.html",
                {
                    "history": history,
                    "error": "Please enter a message."
                }
            )

        if len(message) > MAX_MESSAGE_LENGTH:
            return render(
                request,
                "ai_assistant/chat.html",
                {
                    "history": history,
                    "error": (
                        f"Message is too long. Maximum "
                        f"{MAX_MESSAGE_LENGTH} characters."
                    )
                }
            )

        api_key = os.getenv("GEMINI_API_KEY")

        primary_model = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.8-flash"
        )

        if not api_key:
            return render(
                request,
                "ai_assistant/chat.html",
                {
                    "history": history,
                    "error": (
                        "AI service is not configured. "
                        "Please contact the administrator."
                    )
                }
            )

        client = None

        try:

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=30000
                )
            )

            conversation = []

            for item in history[-MAX_HISTORY_ITEMS:]:

                conversation.append(
                    f"Student: {item['user']}\n"
                    f"Assistant: {item['assistant']}"
                )

            conversation.append(
                f"Student: {message}"
            )

            prompt = (
                "You are an AI Placement Preparation Assistant. "
                "Help students with programming, data structures "
                "and algorithms, DBMS, SQL, operating systems, "
                "computer networks, aptitude, reasoning, technical "
                "and HR interviews, resumes and career guidance. "
                "Explain concepts in simple, friendly language. "
                "Use examples and code when useful. Structure "
                "longer answers with headings and lists. "
                "Do not claim to know the student's actual "
                "performance unless explicitly provided. "
                "If unsure, say so.\n\n"
                "Conversation:\n"
                + "\n\n".join(conversation)
            )

            answer = generate_ai_response(
                client,
                primary_model,
                prompt
            )

            history.append({
                "user": message,
                "assistant": answer
            })

            request.session["ai_chat_history"] = (
                history[-MAX_HISTORY_ITEMS:]
            )

        except Exception:

            logger.exception(
                "Gemini request failed in AI placement assistant"
            )

            return render(
                request,
                "ai_assistant/chat.html",
                {
                    "history": history,
                    "error": (
                        "The AI service is busy right now. "
                        "Please wait a few seconds and try again."
                    )
                }
            )

        finally:

            if client is not None:
                client.close()

    return render(
        request,
        "ai_assistant/chat.html",
        {
            "history": history
        }
    )


@login_required
def clear_chat(request):

    if request.method != "POST":
        return redirect("ai_chat")

    request.session["ai_chat_history"] = []

    return redirect("ai_chat")
