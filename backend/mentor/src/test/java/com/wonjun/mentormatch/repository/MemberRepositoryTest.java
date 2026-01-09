package com.wonjun.mentormatch.repository;

// ▼▼▼ 이 줄이 없어서 에러가 난 것입니다! ▼▼▼
import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.Role;
// ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class MemberRepositoryTest {

    @Autowired
    MemberRepository memberRepository; // 이제 빨간 줄이 사라질 겁니다.

    @Test
    void 회원저장_테스트() {
        // 1. given
        Member member = new Member();
        member.setName("정원준");
        member.setEmail("test@gmail.com");
        member.setPassword("1234");
        member.setRole(Role.MENTOR);

        // 2. when
        Member savedMember = memberRepository.save(member);

        // 3. then
        assertThat(savedMember.getId()).isNotNull();
        assertThat(savedMember.getName()).isEqualTo("정원준");

        System.out.println(">>> 저장된 회원 ID: " + savedMember.getId());
    }
}