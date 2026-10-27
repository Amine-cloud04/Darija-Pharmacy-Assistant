# DawaLink user story

## Customer: prepare a pharmacy question

**As a person looking for a medicine,** I want to explain what I need in Darija, Arabic, French, or a mix, so I can identify the right catalogue item and ask a pharmacy a clear question without guessing its availability.

### The user journey

1. The customer starts with a practical goal: check availability, ask about price, or identify a medicine box.
2. They type naturally or attach a clear photograph of the box. The local Qwen model extracts the goal and any explicitly stated product, strength, form, quantity, and city. Tesseract reads image text locally.
3. If the medicine name is missing, DawaLink asks for it. If several catalogue variants match, the customer compares strength, form, and package size and selects the one printed on their box.
4. DawaLink shows catalogue facts with their uncertainty visible. Price is labelled as a catalogue value; availability is never claimed.
5. The customer chooses whether to ask about availability, price, or both, adds a quantity and city if useful, reviews the message, and copies it to contact their own pharmacy.

### What the customer should be able to rely on

- A medicine candidate comes from a real local catalogue record with a catalogue ID.
- A selected strength must agree with the user’s stated strength. Ambiguous product variants require a choice.
- The local model helps interpret a conversation; it is not the source of medicine or price facts.
- A photo and text are processed on the device by default. Chat prompts go to the local Ollama service, not a hosted model.
- No pharmacy is contacted and no stock, location, or delivery result is invented.

## Pharmacy perspective

A useful enquiry should carry the exact product name, strength, form and package; the quantity wanted; the customer’s city or neighborhood when relevant; and a clear question about availability or price. DawaLink builds that message from a catalogue item and lets the customer check it before copying it.

A pharmacy-facing system would need separate, real integrations: an up-to-date pharmacy directory, each pharmacy’s inventory and price feed, and permissioned messaging or an order workflow. This project has none of those connections, so the customer sends the prepared question through their own channel and receives the real answer from the pharmacy.
