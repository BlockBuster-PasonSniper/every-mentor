package com.wonjun.mentormatch.dto.certification;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
public class OcrVerificationResponseDto {
    private boolean success;
    private String extractedText; // This is the "curriculum" the user mentioned
    private String errorMessage;
}
