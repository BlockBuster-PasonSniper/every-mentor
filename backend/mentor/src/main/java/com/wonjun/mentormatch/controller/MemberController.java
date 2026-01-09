package com.wonjun.mentormatch.controller;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.dto.MemberJoinRequest;
import com.wonjun.mentormatch.repository.MemberRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(name = "회원 관리", description = "회원가입 및 로그인 관련 API") // 1. 컨트롤러 이름
@RestController
@RequestMapping("/api/members")
@RequiredArgsConstructor
public class MemberController {

    private final MemberRepository memberRepository;

    @Operation(summary = "회원가입", description = "이름, 이메일, 비밀번호, 역할(MENTOR/MENTEE)을 입력받아 가입합니다.") // 2. API 설명
    @PostMapping("/join")
    public ResponseEntity<String> join(@RequestBody MemberJoinRequest request) {
        // 1. DTO를 Entity로 변환
        Member member = request.toEntity();

        // 2. 리포지토리를 통해 DB 저장
        memberRepository.save(member);

        return ResponseEntity.ok("회원가입 성공! 이름: " + member.getName());
    }

}


