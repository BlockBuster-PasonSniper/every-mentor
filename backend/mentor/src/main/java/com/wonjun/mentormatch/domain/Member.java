package com.wonjun.mentormatch.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity // 이 클래스가 DB 테이블이 된다는 뜻
@Getter @Setter
@NoArgsConstructor // 기본 생성자 필수
public class Member {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email; // 로그인 아이디

    @Column(nullable = false)
    private String name; // 이름

    private String password;

    // 멘토인지 멘티인지 구분 (MENTOR, MENTEE)
    @Enumerated(EnumType.STRING)
    private Role role;

    // 생성자 편의 메서드 (선택 사항)
    public Member(String email, String name, String password, Role role) {
        this.email = email;
        this.name = name;
        this.password = password;
        this.role = role;
    }
}