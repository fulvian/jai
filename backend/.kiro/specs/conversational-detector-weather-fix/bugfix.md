# Bugfix Requirements Document

## Introduction

Weather queries in Italian (e.g., "Che tempo fa a Caltanissetta?") are incorrectly classified as conversational by the ConversationalDetector, causing the system to bypass tool routing and return generic responses instead of fetching real weather data using the openmeteo_weather tool. This bug prevents users from getting actual weather information when they explicitly request it.

The bug occurs because:
1. The conversational bypass check happens BEFORE domain routing
2. Weather keywords are not in the fast-path regex patterns
3. The LLM prompt in the slow-path is ambiguous and doesn't explicitly list weather queries as tool-requiring

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user asks "Che tempo fa a Caltanissetta?" THEN the system classifies it as conversational and returns "Operazione completata. Non sono stati necessari strumenti aggiuntivi o non sono stati trovati risultati specifici" without calling any weather tools

1.2 WHEN a user asks weather queries like "meteo a Roma", "previsioni Milano", "temperatura Napoli" THEN the system incorrectly classifies them as conversational and bypasses the domain classifier and weather tools

1.3 WHEN the ConversationalDetector's slow-path LLM classification is invoked for weather queries THEN it misclassifies them as conversational because the prompt lacks explicit guidance that weather queries require tools

### Expected Behavior (Correct)

2.1 WHEN a user asks "Che tempo fa a Caltanissetta?" THEN the system SHALL classify it as tool-requiring, route to the geo_weather domain, and call the openmeteo_weather tool to return real weather data

2.2 WHEN a user asks weather queries containing keywords like "tempo", "meteo", "previsioni", "temperatura", "clima" THEN the system SHALL classify them as tool-requiring using fast-path regex matching

2.3 WHEN the ConversationalDetector's slow-path LLM classification is invoked for ambiguous queries THEN it SHALL correctly identify weather queries as tool-requiring based on explicit examples in the prompt

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user asks pure conversational queries like "ciao", "come stai", "grazie" THEN the system SHALL CONTINUE TO classify them as conversational and bypass tool routing

3.2 WHEN a user asks meta questions like "chi sei", "cosa puoi fare" THEN the system SHALL CONTINUE TO classify them as conversational and respond directly

3.3 WHEN a user asks queries requiring other tools (e.g., "prezzo bitcoin", "terremoti recenti", "cerca notizie") THEN the system SHALL CONTINUE TO classify them as tool-requiring and route to the appropriate domain

3.4 WHEN the ConversationalDetector's fast-path regex matches greeting, farewell, or small talk patterns THEN the system SHALL CONTINUE TO classify them as conversational without invoking the LLM slow-path
