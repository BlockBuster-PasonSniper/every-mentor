package com.wonjun.mentormatch.controller;

import com.wonjun.mentormatch.dto.certification.CertificationSaveRequestDto;
import com.wonjun.mentormatch.dto.certification.OcrVerificationResponseDto;
import com.wonjun.mentormatch.service.CertificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/certifications")
@RequiredArgsConstructor
@Tag(name = "Certification", description = "멘토 자격증명 및 OCR API")
public class CertificationController {

    private final CertificationService certificationService;

    @PostMapping("/verify")
    @Operation(summary = "자격증 업로드 및 OCR 검증", description = "멘토가 자격증(Base64)을 업로드하면, 서버는 이를 저장하고 외부 OCR 서비스를 호출하여 검증 결과를 반환합니다.")
    public ResponseEntity<OcrVerificationResponseDto> uploadAndVerifyCertification(@RequestBody CertificationSaveRequestDto requestDto) {
        // TODO: Get memberId from SecurityContextHolder
        Long memberId = 1L; // Placeholder for mentor's ID
        OcrVerificationResponseDto response = certificationService.addCertificationAndVerify(memberId, requestDto);
        return ResponseEntity.ok(response);
    }
}
