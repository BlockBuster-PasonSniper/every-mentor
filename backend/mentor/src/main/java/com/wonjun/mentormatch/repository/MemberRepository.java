package com.wonjun.mentormatch.repository;

import com.wonjun.mentormatch.domain.Member;
import org.springframework.data.jpa.repository.JpaRepository;

// <다룰 엔티티, PK의 타입>
public interface MemberRepository extends JpaRepository<Member, Long> {
    // 아무것도 안 적어도 저장, 조회, 삭제 기능이 자동으로 생깁니다!

    // 나중에 로그인할 때 쓸 메서드 하나만 미리 추가해둘게요.
    // "이메일로 회원을 찾는다"
    boolean existsByEmail(String email);
}