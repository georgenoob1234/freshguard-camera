# Camera Service

A passive camera microservice that captures images on demand. Part of a larger modular computer-vision system, this service is used by the Brain orchestrator to acquire images for processing.

## Features

- **On-demand image capture** via HTTP POST to `/capture`
- **Configurable resolution, format, and quality**
- **Automatic cleanup** of old images based on retention settings
- **Health endpoint** at `/health` for container orchestration

## API Endpoints

| Method | Endpoint                   | Description                        |
|--------|----------------------------|------------------------------------|
| GET    | `/health`                  | Health check (returns `{"status": "healthy"}`) |
| POST   | `/capture`                 | Trigger image capture              |
| GET    | `/api/images/{filename}`   | Retrieve a captured image          |

### Capture Request

```json
POST /capture
{
  "resolution": "320x320",
  "format": "jpeg",
  "quality": 95
}
```

All fields are optional and will use configured defaults if omitted.

## Configuration

The service is configured via environment variables:

| Variable                          | Default       | Description                                      |
|-----------------------------------|---------------|--------------------------------------------------|
| `CAMERA_STORAGE_DIR`              | `./data/images` | Directory for storing captured images          |
| `CAMERA_DEFAULT_RESOLUTION`       | `320x320`     | Default capture resolution                       |
| `CAMERA_DEFAULT_FORMAT`           | `jpeg`        | Default image format (`jpeg` or `png`)           |
| `CAMERA_DEFAULT_QUALITY`          | `95`          | Default JPEG quality (1-100)                     |
| `CAMERA_SOURCE`                   | `0`           | Camera source (`0`, `/dev/video0`, or `dummy`)   |
| `CAMERA_RETENTION_SECONDS`        | `3600`        | How long to keep images before cleanup           |
| `CAMERA_CLEANUP_INTERVAL_SECONDS` | `600`         | Interval between cleanup passes                  |
| `CAMERA_WARMUP_FRAMES`            | `3`           | Frames to discard before capture                 |
| `CAMERA_BUFFER_SIZE`              | `1`           | OpenCV buffer size                               |
| `SERVICE_PORT`                    | `8200`        | Port the service listens on (Docker)             |

## Local Development

### Prerequisites

- Python 3.10+
- A camera device (or use `CAMERA_SOURCE=dummy` for testing)

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the service
./uvicorn.sh
# or
uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload
```

The service will be available at `http://localhost:8200`.

---

## Docker

### Building the Image

```bash
docker build -t camera-service:latest .
```

### Running the Container

```bash
docker run --rm -p 8200:8200 \
  -e SERVICE_PORT=8200 \
  -e CAMERA_SOURCE=dummy \
  -v camera-data:/app/data/images \
  camera-service:latest
```

#### With a Real Camera

To access a physical camera from inside the container, you need to pass the device:

```bash
docker run --rm -p 8200:8200 \
  --device /dev/video0:/dev/video0 \
  -e CAMERA_SOURCE=0 \
  -v camera-data:/app/data/images \
  camera-service:latest
```

### Using Docker Compose

A `docker-compose.yml` is provided for convenience:

```bash
# Start the service
docker compose up -d

# View logs
docker compose logs -f

# Stop the service
docker compose down
```

### Health Check

The container includes a built-in health check. You can also verify manually:

```bash
curl http://localhost:8200/health
# {"status":"healthy","service":"camera"}
```

### Environment Variables for Docker

When running in Docker, you can override any configuration via environment variables:

```bash
docker run --rm -p 8200:8200 \
  -e SERVICE_PORT=8200 \
  -e CAMERA_SOURCE=dummy \
  -e CAMERA_DEFAULT_RESOLUTION=640x480 \
  -e CAMERA_DEFAULT_FORMAT=png \
  -e CAMERA_RETENTION_SECONDS=7200 \
  camera-service:latest
```

---

## Testing

```bash
pytest tests/
```

## License

Internal use only.

