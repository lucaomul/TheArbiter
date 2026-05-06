from arbiter.core.preflight import PreflightValidator


def test_placeholder_detection_flags_todo():
    result = PreflightValidator().validate("Software & IT", "build a script", "TODO: implement logic")
    assert any("Replace placeholders" in issue for issue in result.issues)


def test_scheduling_validation_flags_incomplete_logic():
    task = "Build a shift schedule generator with hours and staff requirements."
    solution = """```javascript
function assign() {
  return schedule;
}
```"""
    result = PreflightValidator().validate("Software & IT", task, solution)
    assert any("Scheduling solution is too incomplete" in issue for issue in result.issues)


def test_marketing_mode_rejects_code_shaped_output():
    task = "Create a 30-day dental clinic go-to-market plan."
    solution = """```python
def launch():
    print("campaign")
```"""
    result = PreflightValidator().validate("Marketing & Growth", task, solution)
    assert any("plain-language deliverable" in issue for issue in result.issues)
