#!/bin/bash

################################################################################
# JAI Monorepo - Copy Large Files Script
################################################################################
#
# PURPOSE:
#   Copy large pre-built files (models, data, node_modules) from source repos
#   instead of re-downloading/rebuilding them. Dramatically speeds up dev setup.
#
# USAGE:
#   ./copy-large-files.sh [OPTIONS] [COMPONENTS]
#
# OPTIONS:
#   -h, --help              Show this help message
#   -d, --dry-run           Show what would be copied without actually copying
#   -v, --verbose           Show detailed progress
#   -s, --skip-validation   Skip size/hash validation after copy
#
# COMPONENTS:
#   backend                 Copy backend models, data, storage (4.9GB)
#   frontend                Copy frontend models, node_modules (4.9GB)
#   all                     Copy all components (9.8GB) [default]
#   models-only             Copy only ML models (8.6GB)
#   data-only               Copy only data and node_modules (1.2GB)
#
# EXAMPLES:
#   ./copy-large-files.sh backend              # Just backend
#   ./copy-large-files.sh frontend             # Just frontend
#   ./copy-large-files.sh all                  # Everything
#   ./copy-large-files.sh -d backend           # Dry-run
#   ./copy-large-files.sh -v all               # Verbose output
#
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
JAI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_BACKEND="/Users/fulvio/coding/Me4BrAIn"
SOURCE_FRONTEND="/Users/fulvio/coding/PersAn"

BACKEND_MODELS="$SOURCE_BACKEND/models"
BACKEND_DATA="$SOURCE_BACKEND/data"
BACKEND_STORAGE="$SOURCE_BACKEND/storage"

FRONTEND_MODELS="$SOURCE_FRONTEND/models"
FRONTEND_NODE_MODULES="$SOURCE_FRONTEND/node_modules"

# Options
DRY_RUN=false
VERBOSE=false
SKIP_VALIDATION=false
COMPONENTS=""

################################################################################
# Helper Functions
################################################################################

print_header() {
  echo -e "${BLUE}===============================================================================${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}===============================================================================${NC}"
}

print_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
  echo -e "${RED}✗ $1${NC}"
}

print_warning() {
  echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
  echo -e "${BLUE}ℹ $1${NC}"
}

get_dir_size() {
  if [[ -d "$1" ]]; then
    du -sh "$1" | awk '{print $1}'
  else
    echo "0B"
  fi
}

get_dir_size_bytes() {
  if [[ -d "$1" ]]; then
    du -sb "$1" | awk '{print $1}'
  else
    echo "0"
  fi
}

show_help() {
  head -n 50 "$0" | tail -n 45
}

validate_source_exists() {
  local source="$1"
  local name="$2"
  
  if [[ ! -d "$source" ]]; then
    print_error "Source not found: $source"
    print_info "Make sure you have cloned the source repository: $SOURCE_BACKEND or $SOURCE_FRONTEND"
    return 1
  fi
}

validate_directory_has_content() {
  local dir="$1"
  local expected_name="$2"
  
  if [[ ! -d "$dir" ]]; then
    return 1
  fi
  
  # Check if directory has any files
  local file_count=$(find "$dir" -type f 2>/dev/null | wc -l || echo "0")
  
  if [[ "$file_count" -eq 0 ]]; then
    return 1
  fi
  
  return 0
}

copy_directory() {
  local source="$1"
  local destination="$2"
  local component_name="$3"
  
  if [[ ! -d "$source" ]]; then
    print_warning "Source not found, skipping: $source"
    return 1
  fi
  
  local src_size=$(get_dir_size "$source")
  
  print_info "Copying $component_name"
  print_info "  Source: $source ($src_size)"
  print_info "  Destination: $destination"
  
  # Create parent directory if needed
  mkdir -p "$(dirname "$destination")"
  
  # Remove destination if it exists and is empty
  if [[ -d "$destination" && -z "$(ls -A "$destination" 2>/dev/null)" ]]; then
    rm -rf "$destination"
  fi
  
  if [[ $DRY_RUN == true ]]; then
    echo "  [DRY-RUN] Would copy: $source -> $destination"
    return 0
  fi
  
  # Use rsync for efficient copying with progress
  if rsync -av --delete \
      --exclude='.git' \
      --exclude='__pycache__' \
      --exclude='.pytest_cache' \
      --exclude='*.pyc' \
      --exclude='.next' \
      --exclude='.turbo' \
      "$source/" "$destination/"; then
    
    local dest_size=$(get_dir_size "$destination")
    print_success "Copied $component_name ($dest_size)"
    return 0
  else
    print_error "Failed to copy $component_name"
    return 1
  fi
}

validate_copy() {
  local source="$1"
  local destination="$2"
  local component_name="$3"
  
  # Skip validation during dry-run (destination doesn't exist yet)
  if [[ $DRY_RUN == true ]]; then
    return 0
  fi
  
  if [[ $SKIP_VALIDATION == true ]]; then
    return 0
  fi
  
  print_info "Validating $component_name..."
  
  local src_files=$(find "$source" -type f 2>/dev/null | wc -l)
  src_files=${src_files## }  # Trim whitespace
  
  local dst_files=$(find "$destination" -type f 2>/dev/null | wc -l)
  dst_files=${dst_files## }  # Trim whitespace
  
  if [[ "$src_files" == "$dst_files" ]]; then
    print_success "Validation passed: $src_files files"
    return 0
  else
    print_warning "File count mismatch: source=$src_files, destination=$dst_files"
    return 1
  fi
}

copy_backend_components() {
  print_header "Copying Backend Components"
  
  if ! validate_source_exists "$SOURCE_BACKEND" "Backend"; then
    print_error "Cannot copy backend without source repository"
    return 1
  fi
  
  local failed=0
  
  # Copy models
  if [[ -d "$BACKEND_MODELS" ]]; then
    if ! copy_directory "$BACKEND_MODELS" "$JAI_ROOT/backend/models" "Backend Models (4.3GB)"; then
      ((failed++))
    else
      if ! validate_copy "$BACKEND_MODELS" "$JAI_ROOT/backend/models" "Backend Models"; then
        ((failed++))
      fi
    fi
  else
    print_warning "Backend models not found: $BACKEND_MODELS"
  fi
  
  # Copy data
  if [[ -d "$BACKEND_DATA" ]]; then
    if ! copy_directory "$BACKEND_DATA" "$JAI_ROOT/backend/data" "Backend Data (497MB)"; then
      ((failed++))
    else
      if ! validate_copy "$BACKEND_DATA" "$JAI_ROOT/backend/data" "Backend Data"; then
        ((failed++))
      fi
    fi
  else
    print_warning "Backend data not found: $BACKEND_DATA"
  fi
  
  # Copy storage
  if [[ -d "$BACKEND_STORAGE" ]]; then
    if ! copy_directory "$BACKEND_STORAGE" "$JAI_ROOT/backend/storage" "Backend Storage (227MB)"; then
      ((failed++))
    else
      if ! validate_copy "$BACKEND_STORAGE" "$JAI_ROOT/backend/storage" "Backend Storage"; then
        ((failed++))
      fi
    fi
  else
    print_warning "Backend storage not found: $BACKEND_STORAGE"
  fi
  
  return $failed
}

copy_frontend_components() {
  print_header "Copying Frontend Components"
  
  if ! validate_source_exists "$SOURCE_FRONTEND" "Frontend"; then
    print_error "Cannot copy frontend without source repository"
    return 1
  fi
  
  local failed=0
  
  # Copy models
  if [[ -d "$FRONTEND_MODELS" ]]; then
    if ! copy_directory "$FRONTEND_MODELS" "$JAI_ROOT/frontend/models" "Frontend Models (4.3GB)"; then
      ((failed++))
    else
      if ! validate_copy "$FRONTEND_MODELS" "$JAI_ROOT/frontend/models" "Frontend Models"; then
        ((failed++))
      fi
    fi
  else
    print_warning "Frontend models not found: $FRONTEND_MODELS"
  fi
  
  # Copy node_modules
  if [[ -d "$FRONTEND_NODE_MODULES" ]]; then
    if ! copy_directory "$FRONTEND_NODE_MODULES" "$JAI_ROOT/frontend/node_modules" "Frontend node_modules (616MB)"; then
      ((failed++))
    else
      if ! validate_copy "$FRONTEND_NODE_MODULES" "$JAI_ROOT/frontend/node_modules" "Frontend node_modules"; then
        ((failed++))
      fi
    fi
  else
    print_warning "Frontend node_modules not found: $FRONTEND_NODE_MODULES"
  fi
  
  return $failed
}

copy_models_only() {
  print_header "Copying Models Only"
  
  local failed=0
  
  if [[ -d "$BACKEND_MODELS" ]]; then
    if ! copy_directory "$BACKEND_MODELS" "$JAI_ROOT/backend/models" "Backend Models (4.3GB)"; then
      ((failed++))
    fi
  fi
  
  if [[ -d "$FRONTEND_MODELS" ]]; then
    if ! copy_directory "$FRONTEND_MODELS" "$JAI_ROOT/frontend/models" "Frontend Models (4.3GB)"; then
      ((failed++))
    fi
  fi
  
  return $failed
}

copy_data_only() {
  print_header "Copying Data & Dependencies Only"
  
  local failed=0
  
  if [[ -d "$BACKEND_DATA" ]]; then
    if ! copy_directory "$BACKEND_DATA" "$JAI_ROOT/backend/data" "Backend Data (497MB)"; then
      ((failed++))
    fi
  fi
  
  if [[ -d "$BACKEND_STORAGE" ]]; then
    if ! copy_directory "$BACKEND_STORAGE" "$JAI_ROOT/backend/storage" "Backend Storage (227MB)"; then
      ((failed++))
    fi
  fi
  
  if [[ -d "$FRONTEND_NODE_MODULES" ]]; then
    if ! copy_directory "$FRONTEND_NODE_MODULES" "$JAI_ROOT/frontend/node_modules" "Frontend node_modules (616MB)"; then
      ((failed++))
    fi
  fi
  
  return $failed
}

show_summary() {
  print_header "Copy Summary"
  
  echo ""
  echo "Backend Files:"
  echo "  Models:  $(get_dir_size "$JAI_ROOT/backend/models" 2>/dev/null || echo "not copied")"
  echo "  Data:    $(get_dir_size "$JAI_ROOT/backend/data" 2>/dev/null || echo "not copied")"
  echo "  Storage: $(get_dir_size "$JAI_ROOT/backend/storage" 2>/dev/null || echo "not copied")"
  echo ""
  echo "Frontend Files:"
  echo "  Models:       $(get_dir_size "$JAI_ROOT/frontend/models" 2>/dev/null || echo "not copied")"
  echo "  node_modules: $(get_dir_size "$JAI_ROOT/frontend/node_modules" 2>/dev/null || echo "not copied")"
  echo ""
}

################################################################################
# Main Script
################################################################################

main() {
  # Parse arguments
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        show_help
        exit 0
        ;;
      -d|--dry-run)
        DRY_RUN=true
        shift
        ;;
      -v|--verbose)
        VERBOSE=true
        shift
        ;;
      -s|--skip-validation)
        SKIP_VALIDATION=true
        shift
        ;;
      backend|frontend|all|models-only|data-only)
        COMPONENTS="$1"
        shift
        ;;
      *)
        print_error "Unknown option: $1"
        echo ""
        show_help
        exit 1
        ;;
    esac
  done
  
  # Default to 'all' if no components specified
  if [[ -z "$COMPONENTS" ]]; then
    COMPONENTS="all"
  fi
  
  # Print header
  print_header "JAI Monorepo - Large Files Copy Script"
  
  if [[ $DRY_RUN == true ]]; then
    print_warning "Running in DRY-RUN mode - no files will be copied"
  fi
  
  print_info "Components to copy: $COMPONENTS"
  print_info "Source backend: $SOURCE_BACKEND"
  print_info "Source frontend: $SOURCE_FRONTEND"
  print_info "Destination: $JAI_ROOT"
  echo ""
  
  # Copy based on selected components
  local total_failed=0
  
  case "$COMPONENTS" in
    backend)
      copy_backend_components || ((total_failed++))
      ;;
    frontend)
      copy_frontend_components || ((total_failed++))
      ;;
    all)
      copy_backend_components || ((total_failed++))
      copy_frontend_components || ((total_failed++))
      ;;
    models-only)
      copy_models_only || ((total_failed++))
      ;;
    data-only)
      copy_data_only || ((total_failed++))
      ;;
  esac
  
  echo ""
  show_summary
  
  if [[ $total_failed -gt 0 ]]; then
    print_error "Copy completed with $total_failed errors"
    exit 1
  else
    print_success "All files copied successfully!"
    print_info "You can now run: ./dev-setup.sh && ./dev-backend.sh && ./dev-frontend.sh"
    exit 0
  fi
}

# Run main function
main "$@"
