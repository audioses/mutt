# MUTT Format Handler Architecture Diagrams

## System Overview

```mermaid
graph TB
    subgraph "Application Layer"
        A[MainFrame - GUI]
        B[Translation Interface]
        C[Review Interface]
    end
    
    subgraph "Format System Core"
        D[FormatManager]
        E[FormatRegistry]
        F[FormatDetector]
    end
    
    subgraph "Format Handlers"
        G[POHandler]
        H[XLIFFHandler]
        I[JSONHandler]
        J[HTMLHandler]
        K[SDLXLIFFHandler]
        L[IDMLHandler]
        M[SRTHandler]
        N[DocXHandler]
    end
    
    subgraph "Internal Format"
        O[TranslationUnit]
        P[Note]
        Q[TranslationStatus]
        R[FormatCapabilities]
    end
    
    A --> D
    B --> D
    C --> D
    D --> E
    D --> F
    E --> G
    E --> H
    E --> I
    E --> J
    E --> K
    E --> L
    E --> M
    E --> N
    G --> O
    H --> O
    I --> O
    O --> P
    O --> Q
    G --> R
```

## Class Hierarchy

```mermaid
classDiagram
    class FormatHandler {
        <<abstract>>
        +format_name: str
        +file_extensions: List[str]
        +mime_types: List[str]
        +format_capabilities: FormatCapabilities
        +can_handle(file_path, content) bool
        +load(file_path, options) List[TranslationUnit]
        +save(units, file_path, options) void
        +validate(units) ValidationResult
        +get_metadata(file_path) Dict
    }
    
    class POHandler {
        +format_name: "GNU Gettext PO"
        +file_extensions: ['.po', '.pot']
        +can_handle() bool
        +load() List[TranslationUnit]
        +save() void
    }
    
    class XLIFFHandler {
        +format_name: "XLIFF"
        +file_extensions: ['.xliff', '.xlf']
        +can_handle() bool
        +load() List[TranslationUnit]
        +save() void
    }
    
    class JSONHandler {
        +format_name: "JSON"
        +file_extensions: ['.json']
        +can_handle() bool
        +load() List[TranslationUnit]
        +save() void
    }
    
    class SDLXLIFFHandler {
        +format_name: "SDL XLIFF"
        +file_extensions: ['.sdlxliff']
        +can_handle() bool
        +load() List[TranslationUnit]
        +save() void
    }
    
    FormatHandler <|-- POHandler
    FormatHandler <|-- XLIFFHandler
    FormatHandler <|-- JSONHandler
    FormatHandler <|-- SDLXLIFFHandler
```

## TranslationUnit Data Model

```mermaid
classDiagram
    class TranslationUnit {
        +id: str
        +source: str
        +target: str
        +source_language: str
        +target_language: str
        +status: TranslationStatus
        +reviewed: bool
        +approved: bool
        +locked: bool
        +context: str
        +notes: List[Note]
        +max_length: Optional[int]
        +placeholders: List[str]
        +quality_score: Optional[float]
        +confidence: Optional[float]
        +fuzzy: bool
        +created_at: Optional[datetime]
        +updated_at: Optional[datetime]
        +translated_by: Optional[str]
        +reviewed_by: Optional[str]
        +attributes: Dict[str, Any]
        +original_format: Optional[str]
        +format_metadata: Dict[str, Any]
    }
    
    class Note {
        +text: str
        +author: str
        +timestamp: datetime
        +type: NoteType
    }
    
    class TranslationStatus {
        <<enumeration>>
        NEW
        TRANSLATED
        REVIEWED
        APPROVED
        NEEDS_WORK
        FINAL
    }
    
    class NoteType {
        <<enumeration>>
        GENERAL
        INSTRUCTION
        ERROR
        QUESTION
        TERMINOLOGY
    }
    
    TranslationUnit --> Note
    TranslationUnit --> TranslationStatus
    Note --> NoteType
```

## Format Detection Flow

```mermaid
flowchart TD
    A[File Input] --> B[Read File Sample]
    B --> C{Extension Match?}
    C -->|Yes| D[Get Extension Handlers]
    C -->|No| E[MIME Type Detection]
    
    D --> F[Test Handler.can_handle()]
    E --> G[Get MIME Handlers]
    G --> H[Test Handler.can_handle()]
    
    F --> I{Handler Found?}
    H --> I
    I -->|Yes| J[Return Handler + Confidence]
    I -->|No| K[Content Analysis Fallback]
    
    K --> L[Test All Handlers]
    L --> M{Any Match?}
    M -->|Yes| N[Return Best Match]
    M -->|No| O[Return None]
```

## Registry Loading Process

```mermaid
sequenceDiagram
    participant App as Application
    participant FM as FormatManager
    participant FR as FormatRegistry
    participant Disc as Auto-Discovery
    
    App->>FM: Initialize
    FM->>FR: Create Registry
    FM->>Disc: auto_discover("format_handlers")
    
    loop For each module
        Disc->>Disc: Import module
        Disc->>Disc: Find FormatHandler subclasses
        Disc->>FR: register(HandlerClass)
        FR->>FR: Create handler instance
        FR->>FR: Build extension maps
        FR->>FR: Build MIME maps
    end
    
    Disc-->>FM: Discovery complete
    FM-->>App: Ready
```

## File Processing Workflow

```mermaid
flowchart TD
    A[User Opens File] --> B[FormatManager.load_file()]
    B --> C{Handler Specified?}
    C -->|Yes| D[Get Specific Handler]
    C -->|No| E[FormatDetector.detect_format()]
    
    D --> F[Handler.can_handle()]
    E --> F
    F --> G{Can Handle?}
    G -->|No| H[Raise Error]
    G -->|Yes| I[Handler.load()]
    
    I --> J[Create TranslationUnits]
    J --> K[Enrich with Metadata]
    K --> L[Return Units + Handler]
    
    L --> M[Convert to Legacy Format]
    M --> N[Display in UI]
```

## Save Process Flow

```mermaid
flowchart TD
    A[User Saves File] --> B[Update TranslationUnits]
    B --> C[FormatManager.save_file()]
    C --> D{Handler Specified?}
    D -->|Yes| E[Get Specific Handler]
    D -->|No| F[Determine from Original Format]
    
    E --> G[Handler.validate()]
    F --> G
    G --> H{Valid?}
    H -->|No| I[Raise ValidationError]
    H -->|Yes| J[Handler.save()]
    
    J --> K[Preserve Format Structure]
    K --> L[Write to File]
    L --> M[Success]
```

## Handler Registration Architecture

```mermaid
graph LR
    subgraph "Format Handler Packages"
        A[localization/]
        B[development/]
        C[office/]
        D[multimedia/]
        E[proprietary/]
    end
    
    subgraph "Auto-Discovery"
        F[Module Scanner]
        G[Class Inspector]
        H[Handler Validator]
    end
    
    subgraph "Registry"
        I[Handler Map]
        J[Extension Map]
        K[MIME Map]
    end
    
    A --> F
    B --> F
    C --> F
    D --> F
    E --> F
    
    F --> G
    G --> H
    H --> I
    H --> J
    H --> K
```

## Format Capabilities Matrix

```mermaid
graph TD
    subgraph "Format Capabilities"
        A[supports_comments]
        B[supports_context]
        C[supports_plural_forms]
        D[supports_fuzzy_matching]
        E[supports_translation_status]
        F[supports_review_workflow]
        G[supports_character_limits]
        H[supports_placeholders]
        I[supports_file_metadata]
        J[supports_inline_elements]
        K[supports_attributes]
        L[binary_format]
        M[preserves_structure]
    end
    
    subgraph "PO Format"
        A --> N[✓]
        B --> O[✓]
        C --> P[✓]
        D --> Q[✓]
        E --> R[✓]
        F --> S[✗]
        G --> T[✗]
        H --> U[✗]
        I --> V[✓]
        J --> W[✗]
        K --> X[✓]
        L --> Y[✗]
        M --> Z[✓]
    end
```

## Error Handling Flow

```mermaid
flowchart TD
    A[Operation Start] --> B{Try Operation}
    B --> C[Handler Operation]
    C --> D{Success?}
    D -->|Yes| E[Return Result]
    D -->|No| F{FormatHandlerError?}
    F -->|Yes| G[Log Format Error]
    F -->|No| H{ValidationError?}
    H -->|Yes| I[Show Validation Issues]
    H -->|No| J[Generic Error Handler]
    
    G --> K[User Notification]
    I --> K
    J --> K
    K --> L[Suggest Actions]
```

## Extension and MIME Type Mapping

```mermaid
graph LR
    subgraph "File Extensions"
        A[.po]
        B[.xliff]
        C[.json]
        D[.sdlxliff]
        E[.idml]
        F[.srt]
    end
    
    subgraph "MIME Types"
        G[text/x-gettext-translation]
        H[application/x-xliff+xml]
        I[application/json]
        J[application/x-sdlxliff+xml]
        K[application/x-adobe-idml]
        L[text/srt]
    end
    
    subgraph "Handlers"
        M[POHandler]
        N[XLIFFHandler]
        O[JSONHandler]
        P[SDLXLIFFHandler]
        Q[IDMLHandler]
        R[SRTHandler]
    end
    
    A --> M
    G --> M
    B --> N
    H --> N
    C --> O
    I --> O
    D --> P
    J --> P
    E --> Q
    K --> Q
    F --> R
    L --> R