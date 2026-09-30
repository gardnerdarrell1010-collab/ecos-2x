"""Build the bounded claim repair from the verified installed preimage."""
import hashlib
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Build a NOT-ACCEPTED local candidate for the race counterexample; never installs it.')
parser.add_argument('--source', type=Path, default=HERE / 'resident_governed.before.py')
source = parser.parse_args().source
assert hashlib.sha256(source.read_bytes()).hexdigest() == '61356177937cf02fe7841a90a059bfa1ea637ad2157eff03982889455c759b47'
text = source.read_text(encoding='utf-8')
marker = '    def claim(self, item, dispatcher_id, run_id):\n'
helper = '''    def _fresh_claim_admission(self, task_id, dispatcher_id):
        """Revalidate NEW ownership; existing owners retain normal drain semantics.

        Settings/capability reads precede the final worker read. Selection and
        old executor evidence never authorize a later ownership write.
        """
        settings = SheetsTable(self.service, self.spreadsheet_id, "Settings")
        maintenance = settings.exact_record({
            "Setting Key": "ECOS_TASK_LOOP_MAINTENANCE_MODE", "Active": "TRUE"})
        if maintenance is None or maintenance[1].get("Value") not in {"TRUE", "FALSE"}:
            return None
        rownum, row = self._find(task_id)
        candidate = EligibleItem(task_id, row)
        decision = fresh_execution_decision(row,
            maintenance=maintenance[1]["Value"] == "TRUE",
            command_supported=lambda command: self.registry.resolve(command, self.capabilities) is not None)
        if not decision.ready:
            self.claimability[task_id] = decision
            return None
        admission = self.executor_local_admission(candidate, dispatcher_id)
        if not admission.get("executable"):
            self.claimability[task_id] = SimpleNamespace(ready=False, reason=admission.get("reason"))
            return None
        # Capability resolution can involve provider reads. Re-resolve the worker
        # after those reads, and reject a changed definition instead of executing
        # a payload whose capabilities were checked against another definition.
        final_rownum, final = self._find(task_id)
        if final_rownum != rownum or final != row:
            return None
        decision = self.validate_selected(EligibleItem(task_id, final))
        self.claimability[task_id] = decision
        return (final_rownum, final) if decision.ready else None

'''
assert text.count(marker) == 1
text = text.replace(marker, helper + marker)
old = '            token=str(uuid.uuid4()); version=int(row.get("Claim Version") or 0)+1; now=_now()'
new = '''            admitted = self._fresh_claim_admission(item.task_id, dispatcher_id)
            if admitted is None:
                return None
            rownum, row = admitted
            token=str(uuid.uuid4()); version=int(row.get("Claim Version") or 0)+1; now=_now()'''
assert text.count(old) == 1
text = text.replace(old, new)
old = '            fresh_rownum, fresh=self._find(item.task_id)\n            if fresh_rownum != rownum'
new = '''            admitted = self._fresh_claim_admission(item.task_id, dispatcher_id)
            if admitted is None:
                return None
            fresh_rownum, fresh = admitted
            if fresh_rownum != rownum'''
assert text.count(old) == 1
text = text.replace(old, new)
# Execution uses the selected payload: changed instructions/stage are deferred to
# the normal next rescan, not executed using the stale selection.
old = '            self.task.update_row(rownum, ["Running", dispatcher_id, token, version, now,'
new = '''            for field in ("Instructions", "Worker Command", "Worker ID", "Worker Type", "Occurrence ID"):
                if fresh.get(field) != item.payload.get(field):
                    return None
            self.task.update_row(rownum, ["Running", dispatcher_id, token, version, now,'''
assert text.count(old) == 1
text = text.replace(old, new)
target = HERE / 'resident_governed.py'
target.write_text(text, encoding='utf-8', newline='\n')
print(hashlib.sha256(target.read_bytes()).hexdigest())
