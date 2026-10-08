"""Keep WASAPI gaps observable without analyzing audio across missing samples."""
import warnings


def record_block(recorder, numframes, warning_category):
    with warnings.catch_warnings(record=True) as caught:
        warnings.filterwarnings("always", message="^data discontinuity in recording$",
                                category=warning_category)
        samples = recorder.record(numframes=numframes)
    gaps = 0
    for warning in caught:
        if issubclass(warning.category, warning_category) and str(warning.message) == "data discontinuity in recording":
            gaps += 1
        else:
            # Preserve unrelated diagnostics after restoring the outer filters.
            warnings.warn_explicit(warning.message, warning.category,
                                   warning.filename, warning.lineno)
    return samples, gaps
