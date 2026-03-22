# ML Models Setup

JAI uses large machine learning models that are **excluded from Git** to keep the repository size manageable. This guide explains how to download and set them up.

## Models Used

### Backend (Me4BrAIn)

**BGE-M3 Embedding Model**
- **Purpose**: Multi-lingual dense embeddings for semantic search
- **Source**: [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
- **Size**: ~2.2GB (PyTorch format)
- **Location**: `backend/src/models/bge-m3-manual/`

### Frontend (PersAn)

No large ML models in frontend. Uses API calls to backend for AI features.

## Setup Instructions

### Option 1: Docker (Recommended)

Models are automatically downloaded on first container startup:

```bash
docker-compose up -d backend
# First startup takes 5-10 minutes for model download
docker-compose logs -f backend
```

### Option 2: Manual Download

#### For Backend

```bash
# Create models directory
mkdir -p backend/src/models

# Download BGE-M3 using huggingface-hub
pip install huggingface-hub

# Download the model
huggingface-cli download BAAI/bge-m3 \
  --local-dir backend/src/models/bge-m3-manual \
  --local-dir-use-symlinks False
```

## Model Configuration

### Environment Variables

Set these in your `.env` file or `docker-compose.yml`:

```env
# Backend model path (relative to backend directory)
EMBEDDING_MODEL_PATH=src/models/bge-m3-manual

# Optional: disable embeddings if models unavailable
USE_EMBEDDINGS=true
```

## Storage Requirements

- **Backend models**: ~2.2GB
- **Build artifacts**: ~500MB (not in git)
- **Total with dependencies**: ~3GB

Ensure your `/tmp` or working directory has at least 5GB free space.

## Troubleshooting

### "Model not found" error

**Solution**: Run model download script:
```bash
cd backend && python scripts/download_models.py
```

### Out of memory during download

**Solution**: Increase Docker memory:
```bash
# In docker-compose.yml, increase backend service memory
services:
  backend:
    mem_limit: 8g
```

### Slow downloads from HuggingFace

**Solution**: Use Hugging Face mirror:
```bash
export HF_ENDPOINT=https://huggingface.co
huggingface-cli download BAAI/bge-m3 ...
```

## Production Deployment

For production deployments, pre-build Docker images with models:

```bash
# Build with models included
docker build \
  --build-arg DOWNLOAD_MODELS=true \
  -t jai-backend:prod \
  backend/
```

## References

- [BAAI BGE-M3 Model Card](https://huggingface.co/BAAI/bge-m3)
- [HuggingFace Hub Documentation](https://huggingface.co/docs/hub/models-downloading)
- [Me4BrAIn Embedding Configuration](./backend/README.md#embeddings)
