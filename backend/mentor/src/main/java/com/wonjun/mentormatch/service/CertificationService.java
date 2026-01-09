package com.wonjun.mentormatch.service;

import com.wonjun.mentormatch.client.OcrClient;
import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.member.Certification;
import com.wonjun.mentormatch.dto.certification.CertificationSaveRequestDto;
import com.wonjun.mentormatch.dto.certification.OcrVerificationResponseDto;
import com.wonjun.mentormatch.exception.ResourceNotFoundException;
import com.wonjun.mentormatch.repository.CertificationRepository;
import com.wonjun.mentormatch.repository.MemberRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional
public class CertificationService {

    private final CertificationRepository certificationRepository;
    private final MemberRepository memberRepository;
    private final OcrClient ocrClient;

    public OcrVerificationResponseDto addCertificationAndVerify(Long memberId, CertificationSaveRequestDto requestDto) {
        Member member = memberRepository.findById(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("Member not found with id: " + memberId));

        // 1. Save the certification image info
        Certification certification = requestDto.toEntity(member);
        certificationRepository.save(certification);

        // 2. Call the external OCR service
        OcrVerificationResponseDto ocrResponse = ocrClient.verify(requestDto.getImageBase64());
        
        // 3. Process the OCR response
        // The user's request on what to do with the response ("curriculum") was ambiguous.
        // For now, we will just log the result and return it to the client.
        // In a real scenario, we might save the extractedText to the member profile,
        // or update the certification status to 'VERIFIED'.
        if (ocrResponse.isSuccess()) {
            System.out.println("OCR verification successful for member " + memberId);
            System.out.println("Extracted Text: " + ocrResponse.getExtractedText());
        } else {
            System.out.println("OCR verification failed for member " + memberId + ": " + ocrResponse.getErrorMessage());
        }

        return ocrResponse;
    }
}
