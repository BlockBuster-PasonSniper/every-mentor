package com.wonjun.mentormatch.controller;

import com.wonjun.mentormatch.dto.application.ApplicationResponseDto;
import com.wonjun.mentormatch.dto.application.ApplicationSaveRequestDto;
import com.wonjun.mentormatch.dto.application.ApplicationStatusUpdateRequestDto;
import com.wonjun.mentormatch.service.ApplicationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.List;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Application", description = "멘토링 신청 API")
public class ApplicationController {

    private final ApplicationService applicationService;

    @PostMapping("/applications")
    @Operation(summary = "멘토링 신청", description = "멘티가 멘토링 공고에 신청합니다.")
    public ResponseEntity<Void> applyToPost(@RequestBody ApplicationSaveRequestDto requestDto) {
        // TODO: Get menteeId from SecurityContextHolder
        Long menteeId = 2L; // Placeholder for mentee's ID
        Long applicationId = applicationService.applyToPost(menteeId, requestDto);
        return ResponseEntity.created(URI.create("/api/applications/" + applicationId)).build();
    }

    @GetMapping("/posts/{postId}/applications")
    @Operation(summary = "특정 공고의 신청 목록 조회", description = "멘토가 자신의 공고에 접수된 신청 목록을 조회합니다.")
    public ResponseEntity<List<ApplicationResponseDto>> getApplicationsByPost(@PathVariable Long postId) {
        // TODO: Get memberId from SecurityContextHolder
        Long memberId = 1L; // Placeholder for mentor's ID
        List<ApplicationResponseDto> responses = applicationService.findApplicationsByPost(postId, memberId);
        return ResponseEntity.ok(responses);
    }

    @PatchMapping("/applications/{applicationId}")
    @Operation(summary = "신청 상태 변경", description = "멘토가 신청 상태를 수락 또는 거절로 변경합니다.")
    public ResponseEntity<Void> updateApplicationStatus(@PathVariable Long applicationId,
                                                      @RequestBody ApplicationStatusUpdateRequestDto requestDto) {
        // TODO: Get memberId from SecurityContextHolder
        Long memberId = 1L; // Placeholder for mentor's ID
        applicationService.updateApplicationStatus(applicationId, memberId, requestDto);
        return ResponseEntity.ok().build();
    }
}
