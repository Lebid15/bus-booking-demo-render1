# OpenAPI Delta — G18 / E19

E19 does not add a separate workflow domain. It strengthens the existing public trip and booking contract by adding versioned policy summaries to public trip responses:

- policy code and immutable version identifier;
- localized summary text;
- full-policy URL scoped to the operating office;
- no full legal markdown embedded in the decision response.

The final generated contract remains **132 paths** and **157 operations**, with **0 validation errors and 0 warnings**.
