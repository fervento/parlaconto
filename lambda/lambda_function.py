import logging
import ask_sdk_core.utils as ask_utils
import openai
import json
import time

from ask_sdk_model.services.directive import (SendDirectiveRequest, Header, SpeakDirective)
from ask_sdk_core.skill_builder import (SkillBuilder, CustomSkillBuilder)
from ask_sdk_core.api_client import DefaultApiClient
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from openai.error import TryAgain
from requests import Timeout

openai.api_key = 'CHANGE-ME'

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SESSION_CONTEXT_KEY = "context"

class GptResponse:
    def __init__(self, gpt_context):
        self.gpt_context = gpt_context

    def get(self, timeout_s):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=self.gpt_context,
                max_tokens=100,
                n=1,
                stop=None,
                temperature=0.5,
                timeout=timeout_s,
                request_timeout=timeout_s
            )

            return response['choices'][0]['message']['content'].strip()
        except Exception as e:
            return None


# Called upon skill invocation
class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        output = "Parlaconto è pronto per il TUO conto"

        with open('mock.json') as mock_file:
            mock_json = json.load(mock_file)

        session_attr = handler_input.attributes_manager.session_attributes
        session_attr[SESSION_CONTEXT_KEY] = [("balance_information", str(mock_json))]

        return handle_speech(handler_input, output, output)


# Handles conversation
class GptQueryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GptQueryIntent")(handler_input)

    def handle(self, handler_input):
        query = handler_input.request_envelope.request.intent.slots["query"].value

        session_attr = handler_input.attributes_manager.session_attributes
        session_context = session_attr[SESSION_CONTEXT_KEY]
        gpt_response = build_gpt_response(session_context, query)
        response = gpt_response.get(timeout_s=5)

        if response:
            session_attr[SESSION_CONTEXT_KEY].append((query, response))
            return handle_speech(handler_input, response)
        else:
            return handle_speech(handler_input, "Non ho capito, prova a richiedere")


# Handles any exception
class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(exception, exc_info=True)

        output = "Scusa non ho capito bene, potresti ripetere la domanda?"

        return handle_speech(handler_input, output, output)


# Handles skill deactivation
class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or ask_utils.is_intent_name(
            "AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        return handle_speech(handler_input, "Parlaconto ti saluta!", "")


# Creates ChatGPT's context
def build_gpt_response(session_context, new_question) -> GptResponse:
    gpt_context = [
        # Creates a specific identity for our assistant
        {
            "role": "system",
            "content": "Sei un assistente bancario capace di prelevare e analizzare i dati bancari dell'utente, rispondendo correttamente a ogni sua esigenza. Ogni transazione bancaria possiede i seguenti attributi: prezzo, valuta, tipologia e data di emissione. Le tue risposte devono essere generate in 5 secondi. Le entrate, di qualsiasi tipologia esse siano sono guadagni in positivo per l'utente. Le uscite, di qualsiasi tipologia esse siano sono una perdita in negativo per l'utente."

        },
        # Context must always contain the user's balance information from which to extrapolate responses
        {
            "role": "system",
            "content": session_context[0][1]
        }
    ]

    # Adds the last 10 interactions to the context to actively engage with the user properly
    for question, answer in session_context[1:][-10:]:
        gpt_context.append({"role": "user", "content": question})
        gpt_context.append({"role": "assistant", "content": answer})

    gpt_context.append({"role": "user", "content": new_question})

    return GptResponse(gpt_context)


def handle_speech(handler_input, speech, ask="Cos'altro posso fare per te?"):
    return (
        handler_input.response_builder
        .speak(speech)
        .ask(ask)
        .response
    )


sb = CustomSkillBuilder(api_client=DefaultApiClient())

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(GptQueryIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()