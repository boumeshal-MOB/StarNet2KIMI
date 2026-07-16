# BTM calculation Lambda handoff

## Purpose

The Lambda is a stateless calculation component. BTM remains the source of truth and is responsible for:

- resolving the project, processing and historically valid configuration version;
- reading raw observations and environmental measurements;
- invoking the Lambda with a complete immutable snapshot;
- storing the run, diagnostics and published values;
- sending generated STAR*NET inputs to the future licensed Windows worker;
- invoking `parse-starnet-outputs` when the worker returns native files.

The Lambda never reads or writes the demo SQLite database.

## Contract

Contract version: `btm.topographic-adjustment.lambda.v1`.

```json
{
  "contract_version": "btm.topographic-adjustment.lambda.v1",
  "request_id": "run-123",
  "operation": "run-processing",
  "payload": {
    "processing_id": 123,
    "processing_name": "NTE network",
    "slot": "2025-03-09T04:00:00.000Z",
    "config": {},
    "raw_observations": [],
    "environment_readings": []
  }
}
```

`run-processing` returns:

- Python least-squares result and diagnostics;
- `success`, `provisional` or `failed` status;
- ready-to-persist X/Y/Z, DX/DY/DZ and SX/SY/SZ output rows;
- STAR*NET `.dat` and `.prj` contents and the physical-point/name mapping.

## Supported operations

- `run-processing`: full stateless processing from a BTM snapshot;
- `calculate`: adjustment from already prepared points and sights;
- `synchronise`, `correct-distance`, `initialise`, `prepare-sights`, `adjust`, `auto-adjust`;
- `build-starnet-inputs`: generate `.dat` and `.prj` without running STAR*NET;
- `parse-starnet-outputs`: parse real `.pts` and `.err` files returned by the Windows worker.

An optional `.lst` file is acknowledged but intentionally not interpreted until golden files from the licensed STAR*NET version are available.

## Deployment

The scientific stack includes NumPy and SciPy, so the supported deployment is a Lambda container image:

```bash
docker build -f Dockerfile.lambda -t btm-topographic-lambda .
```

For AWS SAM:

```bash
sam build -t template.lambda.yaml
sam deploy --guided
```

Recommended initial configuration is 2 GB memory, 15-minute timeout and 1 GB `/tmp`. The function itself does not require persistent local storage.

## STAR*NET future workflow

```text
BTM snapshot
  -> calculation Lambda
  -> Python result + input.dat + project.prj
  -> BTM stores immutable artifacts
  -> licensed Windows worker executes STAR*NET Ultimate
  -> worker returns .pts/.err/.lst
  -> Lambda parse-starnet-outputs
  -> BTM compares/approves/publishes the certified result
```

The current Lambda does not simulate execution of STAR*NET. It only generates real input contracts and parses returned native outputs.
