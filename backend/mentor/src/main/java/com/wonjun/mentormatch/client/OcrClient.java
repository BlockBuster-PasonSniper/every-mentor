package com.wonjun.mentormatch.client;

import com.wonjun.mentormatch.dto.certification.OcrVerificationResponseDto;
import org.springframework.stereotype.Component;

@Component
public class OcrClient {

    /**
     * Simulates calling an external OCR service.
     * @param imageBase64 The Base64 encoded image string.
     * @return A simulated response from the OCR service.
     */
    public OcrVerificationResponseDto verify(String imageBase64) {
        // In a real application, this would use RestTemplate or WebClient
        // to call the external OCR service endpoint.
        // For now, we just simulate a successful response.

        System.out.println("--- Calling External OCR Service ---");
        System.out.println("Image length: " + (imageBase64 != null ? imageBase64.length() : 0));
        System.out.println("--- OCR Service Called ---");

        // Simulate a response
        OcrVerificationResponseDto mockResponse = new OcrVerificationResponseDto();
        mockResponse.setSuccess(true);
        mockResponse.setExtractedText("Extracted Curriculum Vitae: [Details from OCR]");
        return mockResponse;
    }
}
