from pathlib import Path
from sources.document import SourceDocument
from common.logging_setup import AppLogger
from processing.frontmatter_parser import FrontmatterParser

logger = AppLogger.get_logger()


class FilesystemLoader:
    IGNORE_FILES = {"readme.md", "_index.md"}
    IGNORE_DIRS = {".git", "_build"}

    def __init__(self, root: Path):
        self.root = root

    def load(self):
        logger.info(f"FilesystemLoader started. Root: {self.root}")

        documents = []
        scanned_count = 0
        ignored_count = 0
        error_count = 0

        for file in self.root.rglob("*.md"):
            scanned_count += 1

            if file.name.lower() in self.IGNORE_FILES:
                ignored_count += 1
                logger.debug(f"Ignoring file '{file}' because it is in IGNORE_FILES")
                continue

            if any(part in self.IGNORE_DIRS for part in file.parts):
                ignored_count += 1
                logger.debug(f"Ignoring file '{file}' because path contains ignored directory")
                continue

            try:
                text = file.read_text(encoding="utf-8")

            except Exception as exc:
                error_count += 1
                logger.warning(f"Could not read file '{file}': {exc}")
                continue

            try:
                frontmatter_metadata, cleaned_text = FrontmatterParser.parse(text)
            except Exception as exc:
                error_count += 1
                logger.warning(f"Could not parse file '{file}': {exc}")
                continue

            try:
                path_metadata = self.extract_metadata(file, self.root)
            except Exception as exc:
                error_count += 1
                logger.warning(f"Could not extract metadata for file '{file}': {exc}")
                continue

            metadata = {**path_metadata, **frontmatter_metadata}

            document = SourceDocument(
                id=str(file),
                title=metadata.pop("title", file.stem),
                text=cleaned_text,
                source="filesystem",
                path=str(file),
                metadata=metadata,
            )

            documents.append(document)

            logger.info(f"Loaded document: {file}")
            logger.debug(f"Metadata for '{file.name}': {metadata}")

        logger.info(
            f"FilesystemLoader finished. "
            f"Scanned={scanned_count}, Loaded={len(documents)}, "
            f"Ignored={ignored_count}, Errors={error_count}"
        )

        return documents

    @staticmethod
    def extract_metadata(path: Path, root: Path) -> dict:
        relative = path.relative_to(root)
        parts = relative.parts

        metadata = {
            "loader": "filesystem",
            "filename": path.name,
            "type": "markdown",
            "extension": path.suffix.lower(),
            "file_size": path.stat().st_size,
            "relative_path": str(relative),
        }

        if not parts:
            return metadata

        metadata["domain"] = parts[0]

        if parts[0] == "sap":
            if "platform" in parts:
                idx = parts.index("platform")
                metadata["scope"] = "platform"

                if len(parts) > idx + 1:
                    metadata["platform_area"] = parts[idx + 1]

                if len(parts) > idx + 2:
                    metadata["platform_subarea"] = parts[idx + 2]

            if "customers" in parts:
                idx = parts.index("customers")
                metadata["scope"] = "customer"

                if len(parts) > idx + 1:
                    metadata["customer"] = parts[idx + 1]

            if "projects" in parts:
                idx = parts.index("projects")
                metadata["scope"] = "project"

                if len(parts) > idx + 1:
                    metadata["project"] = parts[idx + 1]

                if len(parts) > idx + 2:
                    metadata["category"] = parts[idx + 2]

        else:
            if len(parts) > 1:
                metadata["category"] = parts[1]
            if len(parts) > 2:
                metadata["subcategory"] = parts[2]

        return metadata