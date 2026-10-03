# Report Architecture

The application uses a plug-in style structure so new report formats do not modify existing report logic.

## Structure

```
app.py                       # login, connection status, report dispatcher only
report_runtime.py            # shared secrets / auth / date helpers
reports/
  registry.py                # the only place that registers report types
  explore/
    report.py                # Explore UI + orchestration
  pd_bc/
    parser.py                # PD+BC CSV parser
    report.py                # PD+BC UI + orchestration (when enabled)
    ppt.py                   # PD+BC PowerPoint generator (when enabled)
```

Existing low-level integrations such as `gsc_client.py`, `screenshot.py`, and `gemini_analyzer.py`
are shared services. Report-specific parsing, calculations, slide mapping, Streamlit state, and UI must
stay inside each report package.

## Rules for a new report

1. Create `reports/<report_key>/`.
2. Keep its CSV parser in that package.
3. Keep its PowerPoint/template mapping in that package.
4. Keep all Streamlit widget/session keys namespaced with the report key.
5. Do not import another report package.
6. Add exactly one entry to `reports/registry.py` when the report is production-ready.
7. Add report-specific tests before enabling it in the registry.

This means an unfinished report can be developed without appearing in the production UI and without
changing the Explore generator.
