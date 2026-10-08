Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 11A. Test Coverage and Observability Cross-Reference

The Test Strategy v1.8 is authoritative for coverage, release, live-dependency, and trace evidence.

Code coverage gates use the Optimus product group and separate context_engine / optimus_model_policy 80% floors; all-source aggregate is informational, with safety-critical modules
protected from regression. OTel/OTLP trace assertions validate debugging and regression fields but
do not count toward code coverage.

| Evidence class | Required dependency |
|---|---|
| Unit | Fakes allowed; no network/I/O unless intrinsic |
| Redis integration | Real TimeSeries-capable Redis |
| Gateway live | Real Optimus credentials and live local Gateway |
| ACP protocol | Independent `acpx` client |
| Trace live | Real OTLP export to Phoenix |
| Release | Agent/Gateway credential and egress scopes proven separately |

LangSmith trace assertions and amortized observability accounting are deleted.