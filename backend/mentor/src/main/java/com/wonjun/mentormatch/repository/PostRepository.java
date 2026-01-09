package com.wonjun.mentormatch.repository;

import com.wonjun.mentormatch.domain.post.Post;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PostRepository extends JpaRepository<Post, Long> {
}
