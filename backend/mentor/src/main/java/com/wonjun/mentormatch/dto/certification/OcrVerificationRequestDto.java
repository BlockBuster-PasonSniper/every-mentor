package com.wonjun.mentormatch.dto.certification;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class OcrVerificationRequestDto {
    private String imageBase64;
}
